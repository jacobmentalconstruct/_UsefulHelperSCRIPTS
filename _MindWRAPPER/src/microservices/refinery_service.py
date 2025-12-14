import json
from typing import Dict, Any, Optional
from .base_service import BaseService
from .cartridge_service import CartridgeService
from .neural_service import NeuralService
from .semantic_chunker import SemanticChunker

class RefineryService(BaseService):
    """
    The Night Shift (v2).
    Chunks code, generates vectors, and enriches metadata.
    """

    def __init__(self, cartridge: CartridgeService, neural: NeuralService):
        super().__init__("RefineryService")
        self.cartridge = cartridge
        self.neural = neural
        self.chunker = SemanticChunker()

    def process_pending_files(self, batch_size: int = 10) -> int:
        pending = self.cartridge.get_pending_files(limit=batch_size)
        if not pending: return 0

        self.log_info(f"Refining {len(pending)} files (Chunking + Vectorizing)...")
        results = self.neural.process_parallel(pending, self._process_single_file)
        return len(results)

    def _process_single_file(self, file_row: Dict) -> bool:
        file_id = file_row["id"]
        path = file_row["path"]
        content = file_row["content"]
        
        if not content:
            # Binary file? Mark processed but don't chunk
            self.cartridge.update_file_status(file_id, "SKIPPED_BINARY")
            return True

        try:
            # 1. Semantic Chunking
            chunks = self.chunker.chunk_file(content, path)
            
            # 2. Vectorization Loop
            conn = self.cartridge._get_conn()
            cursor = conn.cursor()
            
            for i, chunk in enumerate(chunks):
                # Get Vector from CPU Embedder
                vector = self.neural.get_embedding(chunk.content)
                vec_blob = json.dumps(vector).encode('utf-8') if vector else None
                
                cursor.execute("""
                    INSERT INTO chunks (file_id, chunk_index, content, embedding, name, type, start_line, end_line)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (file_id, i, chunk.content, vec_blob, chunk.name, chunk.type, chunk.start_line, chunk.end_line))
            
            conn.commit()
            conn.close()

            # 3. Metadata Enrichment (The 1.5b-coder pass)
            meta = {}
            if path.endswith(".py"):
                meta = self._analyze_python(content)
            
            self.cartridge.update_file_status(file_id, "ENRICHED", metadata=meta)
            return True

        except Exception as e:
            self.log_error(f"Refinery failed on {path}: {e}")
            self.cartridge.update_file_status(file_id, "ERROR", metadata={"error": str(e)})
            return False

    def _analyze_python(self, content: str) -> Dict:
        """Ask 1.5b-coder for a structural summary."""
        prompt = f"""
        Analyze this Python code. Return JSON with:
        - "summary": "One sentence description"
        - "complexity": "Low/Medium/High"
        
        Code:
        {content[:2000]}
        """
        response = self.neural.request_inference(prompt, tier="fast", format_json=True)
        try: return json.loads(response)
        except: return {"summary": "Analysis failed"}
