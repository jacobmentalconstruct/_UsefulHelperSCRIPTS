import json
import re
import concurrent.futures
from typing import Dict, List
from .base_service import BaseService
from .cartridge_service import CartridgeService
from .neural_service import NeuralService
from .semantic_chunker import SemanticChunker

class RefineryService(BaseService):
    """
    The Night Shift.
    Polls the DB for 'RAW' files and processes them into Chunks and Graph Nodes.
    """

    def __init__(self, cartridge: CartridgeService, neural: NeuralService):
        super().__init__("RefineryService")
        self.cartridge = cartridge
        self.neural = neural
        self.chunker = SemanticChunker()
        
        # Simple regex for imports (Python/JS)
        self.import_pattern = re.compile(r'(?:from|import)\s+([\w\.]+)|require\([\'"]([\w\.\-/]+)[\'"]\)')

    def process_pending(self, batch_size: int = 5) -> int:
        """Main loop. Returns number of files processed."""
        pending = self.cartridge.get_pending_files(limit=batch_size)
        if not pending: return 0

        self.log_info(f"Refining batch of {len(pending)} files...")
        
        for file_row in pending:
            self._refine_file(file_row)
            
        return len(pending)

    def _refine_file(self, row: Dict):
        file_id = row['id']
        vfs_path = row['vfs_path']
        content = row['content']
        
        # Skip binary files for now (unless we add OCR later)
        if not content:
            self.cartridge.update_status(file_id, "SKIPPED_BINARY")
            return

        try:
            # 1. Semantic Chunking
            chunks = self.chunker.chunk_file(content, vfs_path)
            
            # 2. Vectorization & Storage
            # Parallel Embedding: Gather all texts first
            chunk_texts = [c.content for c in chunks]
            vectors = []
            
            # Use ThreadPool to embed in parallel (preserve order with map)
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.neural.max_workers) as executor:
                vectors = list(executor.map(self.neural.get_embedding, chunk_texts))

            conn = self.cartridge._get_conn()
            for i, chunk in enumerate(chunks):
                
                vector = vectors[i]
                vec_blob = json.dumps(vector).encode('utf-8') if vector else None
                
                # Store Chunk
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO chunks (file_id, chunk_index, content, embedding, name, type, start_line, end_line)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (file_id, i, chunk.content, vec_blob, chunk.name, chunk.type, chunk.start_line, chunk.end_line))
                
                # Capture the ID of the chunk we just made
                chunk_row_id = cursor.lastrowid
                
                # Insert into Vector Index (if vector exists)
                if vector:
                    try:
                        # We use json.dumps for compatibility with sqlite-vec via standard python sqlite3
                        cursor.execute("INSERT INTO vec_items(rowid, embedding) VALUES (?, ?)", 
                                     (chunk_row_id, json.dumps(vector)))
                    except Exception as ve:
                        self.log_error(f"Vector Index Insert Failed: {ve}")

                # Graph Node for Chunks (Functions/Classes)
                if chunk.type in ['class', 'function']:
                    node_id = f"{vfs_path}::{chunk.name}"
                    self.cartridge.add_node(node_id, 'chunk', chunk.name, {'parent': vfs_path})
                    self.cartridge.add_edge(node_id, vfs_path, "defined_in")

            conn.commit()
            conn.close()

            # 3. File Level Graph Node
            self.cartridge.add_node(vfs_path, 'file', vfs_path.split('/')[-1], {'path': vfs_path})

            # 4. Import Weaving (Simple)
            self._weave_imports(vfs_path, content)

            self.cartridge.update_status(file_id, "REFINED")

        except Exception as e:
            self.log_error(f"Refining failed for {vfs_path}: {e}")
            self.cartridge.update_status(file_id, "ERROR", {"error": str(e)})

    def _weave_imports(self, source_path: str, content: str):
        """Scans content for imports and links them in the graph."""
        lines = content.splitlines()
        for line in lines:
            match = self.import_pattern.search(line)
            if match:
                # Extract the import name (e.g., 'os', 'numpy', './utils')
                imp = match.group(1) or match.group(2)
                if imp:
                    # Heuristic: Link to any node ID that contains this string
                    # Real implementation would do path resolution, but this creates the visual structure effectively.
                    self.cartridge.add_edge(source_path, imp, "imports")

