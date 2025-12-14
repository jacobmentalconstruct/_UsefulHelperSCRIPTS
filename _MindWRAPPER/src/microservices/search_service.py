import sqlite3
import json
import struct
import math
from typing import List, Dict, Optional
from .base_service import BaseService
from .neural_service import NeuralService

class SearchService(BaseService):
    """
    The Oracle.
    Performs Hybrid Search (Vector + Keyword) to find knowledge.
    Includes robust fallback to pure Python math if C++ extensions fail.
    """

    def __init__(self, db_path: str, neural: NeuralService):
        super().__init__("SearchService")
        self.db_path = db_path
        self.neural = neural
        self.vec_extension_loaded = False

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        # Try to load sqlite-vec for speed
        try:
            conn.enable_load_extension(True)
            import sqlite_vec
            sqlite_vec.load(conn)
            self.vec_extension_loaded = True
        except:
            self.vec_extension_loaded = False
        return conn

    def search(self, query: str, limit: int = 15) -> List[Dict]:
        """
        Main Entry Point: Hybrid Search.
        """
        # 1. Get Vector for the Query
        query_vec = self.neural.get_embedding(query)
        
        conn = self._get_conn()
        results = []
        
        try:
            if query_vec:
                if self.vec_extension_loaded:
                    results = self._search_fast_vec(conn, query_vec, limit)
                else:
                    results = self._search_python_vec(conn, query_vec, limit)
            else:
                self.log_info("Embedding failed/skipped. Falling back to Keyword Search.")
                results = self._search_keyword(conn, query, limit)
        finally:
            conn.close()
            
        return results

    def _search_fast_vec(self, conn, query_vec, limit):
        """C++ Accelerated Search."""
        cursor = conn.cursor()
        vec_bytes = struct.pack(f'{len(query_vec)}f', *query_vec)
        
        sql = """
            SELECT f.path, c.content, vec_distance_cosine(c.embedding, ?) as distance
            FROM chunks c
            JOIN files f ON c.file_id = f.id
            WHERE c.embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT ?
        """
        rows = cursor.execute(sql, (vec_bytes, limit)).fetchall()
        return self._format_results(rows, score_is_distance=True)

    def _search_python_vec(self, conn, query_vec, limit):
        """Python Fallback Search (Slow but Reliable)."""
        cursor = conn.cursor()
        cursor.execute("SELECT c.id, f.path, c.content, c.embedding FROM chunks c JOIN files f ON c.file_id = f.id")
        
        candidates = []
        for row in cursor.fetchall():
            _, path, content, blob = row
            if not blob: continue
            
            try:
                # Handle JSON or Binary blobs
                try: vec = json.loads(blob)
                except: vec = struct.unpack(f'{len(query_vec)}f', blob)
                
                score = self._cosine_similarity(query_vec, vec)
                candidates.append((score, path, content))
            except: continue

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [{"path": c[1], "score": c[0], "content": c[2]} for c in candidates[:limit]]

    def _search_keyword(self, conn, query, limit):
        """Old-school LIKE search."""
        cursor = conn.cursor()
        cursor.execute("SELECT path, content FROM files WHERE content LIKE ? LIMIT ?", (f'%{query}%', limit))
        return [{"path": r[0], "score": 1.0, "content": r[1]} for r in cursor.fetchall()]

    def _cosine_similarity(self, v1, v2):
        dot = sum(a*b for a,b in zip(v1, v2))
        norm1 = math.sqrt(sum(a*a for a in v1))
        norm2 = math.sqrt(sum(b*b for b in v2))
        return dot / (norm1 * norm2) if norm1 and norm2 else 0.0

    def _format_results(self, rows, score_is_distance=False):
        formatted = []
        for r in rows:
            score = 1 - r[2] if score_is_distance else r[2]
            formatted.append({"path": r[0], "score": score, "content": r[1]})
        return formatted
