import sqlite3
import json
import struct
import requests
import os
import math
from typing import List, Dict, Any, Optional

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api"

class SearchEngineMS:
    """
    The Oracle: Performs Hybrid Search (Vector Similarity + Keyword Matching).
    Includes a pure-Python fallback for vector math if sqlite-vec is missing.
    """

    def __init__(self, embed_model: str = "nomic-embed-text"):
        self.embed_model = embed_model
        self.vec_extension_loaded = False

    def _load_extension(self, conn: sqlite3.Connection):
        """Attempts to load sqlite-vec if available."""
        try:
            conn.enable_load_extension(True)
            import sqlite_vec
            sqlite_vec.load(conn)
            self.vec_extension_loaded = True
        except (ImportError, AttributeError, sqlite3.OperationalError):
            # Silently fail and fallback to Python math
            self.vec_extension_loaded = False

    def search(self, db_path: str, query: str, limit: int = 10) -> List[Dict]:
        if not os.path.exists(db_path):
            return []

        conn = sqlite3.connect(db_path)
        self._load_extension(conn)
        cursor = conn.cursor()

        # 1. Vectorize Query
        query_vec = self._get_query_embedding(query)
        if not query_vec:
            # Fallback to keyword only if embedding fails (e.g. Ollama offline)
            conn.close()
            return self._keyword_search_fallback(db_path, query, limit)

        results = []
        
        try:
            if self.vec_extension_loaded:
                # FAST PATH: C++ Extension
                results = self._search_sqlite_vec(cursor, query_vec, limit)
            else:
                # SLOW PATH: Python Math (Robustness)
                results = self._search_pure_python(cursor, query_vec, limit)
        except Exception as e:
            print(f"[SearchEngine] Error: {e}")
            results = self._keyword_search_fallback(db_path, query, limit)

        conn.close()
        return results

    def _search_sqlite_vec(self, cursor, query_vec: List[float], limit: int) -> List[Dict]:
        """Used when sqlite-vec is successfully loaded."""
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

    def _search_pure_python(self, cursor, query_vec: List[float], limit: int) -> List[Dict]:
        """
        Fallback: Fetches all embeddings and computes Cosine Similarity in Python.
        Slower, but guarantees functionality without DLL dependencies.
        """
        sql = "SELECT c.id, f.path, c.content, c.embedding FROM chunks c JOIN files f ON c.file_id = f.id"
        cursor.execute(sql)
        
        candidates = []
        for row in cursor.fetchall():
            chunk_id, path, content, blob = row
            if not blob: continue
            
            try:
                # Deserialize: Try JSON first (as per your IngestEngine), then struct
                try:
                    vec = json.loads(blob)
                except:
                    # Fallback for binary blob if changed later
                    vec = struct.unpack(f'{len(query_vec)}f', blob)
                
                score = self._cosine_similarity(query_vec, vec)
                candidates.append((score, path, content))
            except Exception:
                continue

        # Sort by Score DESC (High similarity is better)
        candidates.sort(key=lambda x: x[0], reverse=True)
        top_n = candidates[:limit]
        
        return [{
            "path": r[1],
            "score": r[0],
            "snippet": r[2][:200].replace('\n', ' ') + "...",
            "full_content": r[2]
        } for r in top_n]

    def _keyword_search_fallback(self, db_path: str, query: str, limit: int) -> List[Dict]:
        """Used if Ollama is dead or vectors fail completely."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        sql = "SELECT path, content FROM files WHERE content LIKE ? LIMIT ?"
        rows = cursor.execute(sql, (f'%{query}%', limit)).fetchall()
        conn.close()
        return [{
            "path": r[0],
            "score": 0.0,
            "snippet": r[1][:200].replace('\n', ' ') + "...",
            "full_content": r[1]
        } for r in rows]

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

    def _get_query_embedding(self, text: str) -> Optional[List[float]]:
        try:
            res = requests.post(
                f"{OLLAMA_API_URL}/embeddings",
                json={"model": self.embed_model, "prompt": text},
                timeout=5
            )
            if res.status_code == 200:
                return res.json().get("embedding")
        except:
            pass
        return None

    def _format_results(self, rows, score_is_distance=False):
        results = []
        for r in rows:
            score = r[2]
            # Convert Cosine Distance (0..2) to Similarity (0..1)
            if score_is_distance:
                score = 1 - score 
            
            results.append({
                "path": r[0],
                "score": score,
                "snippet": r[1][:200].replace('\n', ' ') + "...",
                "full_content": r[1]
            })
        return results

if __name__ == "__main__":
    print("SearchEngineMS Ready.")