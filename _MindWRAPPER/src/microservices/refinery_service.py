import json
import re
import os
import sqlite3
from typing import Dict, Any, Optional, List
from .base_service import BaseService
from .cartridge_service import CartridgeService
from .neural_service import NeuralService
from .semantic_chunker import SemanticChunker

class SynapseWeaver:
    """
    Helper class to extract dependencies from code.
    Moved from _NeoCORTEX to ensure silent graph building.
    """
    def __init__(self):
        # Regex for Python imports
        self.py_import = re.compile(r'^\s*(?:from|import)\s+([\w\.]+)')
        # Regex for JS/TS imports
        self.js_import = re.compile(r'(?:import\s+.*?from\s+[\'"]|require\([\'"])([\.\/\w\-_]+)[\'"]')

    def extract(self, content: str, filename: str) -> List[str]:
        deps = set()
        if not content: return []
        
        lines = content.splitlines()
        is_py = filename.endswith('.py')
        is_js = filename.endswith(('.js', '.ts', '.jsx', '.tsx'))

        if not (is_py or is_js):
            return []

        for line in lines:
            match = None
            if is_py:
                match = self.py_import.match(line)
            elif is_js:
                match = self.js_import.search(line)
            
            if match:
                # Clean up the import (e.g., 'src.utils' -> 'utils')
                raw = match.group(1)
                clean = raw.split('.')[-1].split('/')[-1]
                deps.add(clean)
        
        return list(deps)

class RefineryService(BaseService):
    """
    The Night Shift (v3 - Graph Aware).
    Chunks code, generates vectors, and WEAVES connections automatically.
    """

    def __init__(self, cartridge: CartridgeService, neural: NeuralService):
        super().__init__("RefineryService")
        self.cartridge = cartridge
        self.neural = neural
        self.chunker = SemanticChunker()
        self.weaver = SynapseWeaver()

    def process_pending_files(self, batch_size: int = 10) -> int:
        pending = self.cartridge.get_pending_files(limit=batch_size)
        if not pending: return 0

        self.log_info(f"Refining {len(pending)} files (Chunking + Vectorizing + Weaving)...")
        # We process serially or parallel. For graph weaving, serial is safer for SQLite locking,
        # but since we are just reading/writing, parallel is okay if SQLite handles concurrency well.
        # Sticking to parallel for speed.
        results = self.neural.process_parallel(pending, self._process_single_file)
        return len(results)

    def _process_single_file(self, file_row: Dict) -> bool:
        file_id = file_row["id"]
        path = file_row["path"]
        content = file_row["content"]
        
        if not content:
            self.cartridge.update_file_status(file_id, "SKIPPED_BINARY")
            return True

        try:
            # --- 1. Semantic Chunking ---
            chunks = self.chunker.chunk_file(content, path)
            
            # --- 2. Vectorization ---
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
                
                # Create a "Satellite Node" for important chunks (Classes/Functions)
                if chunk.type in ['class', 'function']:
                    chunk_node_id = f"{path}::{chunk.name}"
                    cursor.execute("""
                        INSERT OR REPLACE INTO graph_nodes (id, type, label, data_json)
                        VALUES (?, 'chunk', ?, ?)
                    """, (chunk_node_id, chunk.name, json.dumps({'parent': path})))
                    
                    # Link Chunk -> File
                    cursor.execute("INSERT OR IGNORE INTO graph_edges (source, target, relation) VALUES (?, ?, 'defined_in')", 
                                   (chunk_node_id, path))

            conn.commit()
            conn.close()

            # --- 3. Weaving (Dependency Graph) ---
            self._weave_dependencies(path, content)

            # --- 4. Metadata Enrichment ---
            meta = {}
            if path.endswith(".py"):
                meta = self._analyze_python(content)
            
            self.cartridge.update_file_status(file_id, "ENRICHED", metadata=meta)
            return True

        except Exception as e:
            self.log_error(f"Refinery failed on {path}: {e}")
            self.cartridge.update_file_status(file_id, "ERROR", metadata={"error": str(e)})
            return False

    def _weave_dependencies(self, source_path: str, content: str):
        """Finds imports and attempts to link them to existing files in the DB."""
        dependencies = self.weaver.extract(content, source_path)
        if not dependencies: return

        conn = self.cartridge._get_conn()
        cursor = conn.cursor()
        
        for dep in dependencies:
            # Search for the dependency in the DB (fuzzy match on filename)
            # We look for a file that ends with 'dep.py' or 'dep.js'
            # This is a heuristic but efficient.
            query = f"%/{dep}.%" # e.g. %/utils.% matches src/utils.py
            
            # Also try exact match for flat directories
            query_exact = f"{dep}.%"

            cursor.execute("SELECT path FROM files WHERE path LIKE ? OR path LIKE ?", (query, query_exact))
            result = cursor.fetchone()

            if result:
                target_path = result[0]
                if target_path != source_path:
                    # Found a link!
                    self.cartridge.add_edge(source_path, target_path, relation="imports")
            else:
                # Broken Link / External Library
                self.cartridge.log_unresolved_import(source_path, dep)

        conn.close()

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