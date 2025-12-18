import sqlite3
import json
import struct
import requests
import os
from typing import List, Dict, Any, Optional

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api"

class SearchEngineMS:
    """
    The Oracle: Performs Hybrid Search (Vector Similarity + Keyword Matching).
    
    Architecture:
    1. Vector Search: Uses sqlite-vec (vec0) for fast nearest neighbor search.
    2. Keyword Search: Uses SQLite FTS5 for BM25-style text matching.
    3. Reranking: Combines scores using Reciprocal Rank Fusion (RRF).
    """

    def __init__(self, model_name: str = "phi3:mini-128k"):
        self.model = model_name

    def search(self, db_path: str, query: str, limit: int = 10) -> List[Dict]:
        """
        Main entry point. Returns a list of results sorted by relevance.
        """
        if not os.path.exists(db_path):
            return []

        conn = sqlite3.connect(db_path)
        # Enable sqlite-vec extension if needed, though standard connect might miss it 
        # depending on system install. For now, we assume the DB is pre-populated 
        # and standard SQL queries work if the extension is loaded globally or unnecessary 
        # for simple selects (standard SQLite can read vec0 tables usually, just not query them efficiently without ext).
        # Note: If sqlite-vec is not loaded, the vec0 MATCH queries below will fail.
        # We try to load it here just in case.
        conn.enable_load_extension(True)
        try:
            import sqlite_vec
            sqlite_vec.load(conn)
        except:
            print("Warning: sqlite_vec not loaded in Search Engine. Vector search may fail.")

        cursor = conn.cursor()

        # 1. Vectorize the User Query
        query_vec = self._get_query_embedding(query)
        if not query_vec:
            # Fallback to keyword only if embedding fails
            return self._keyword_search_only(cursor, query, limit)

        # Pack vector for sqlite-vec (Float32 Little Endian)
        vec_bytes = struct.pack(f'{len(query_vec)}f', *query_vec)

        # 2. HYBRID QUERY (The "Magic" SQL)
        # We use CTEs to get top 50 from Vector and top 50 from Keyword, then merge.
        sql = """
        WITH 
        vec_matches AS (
            SELECT rowid, distance,
            row_number() OVER (ORDER BY distance) as rank
            FROM knowledge_vectors
            WHERE embedding MATCH ? 
            AND k = 50
        ),
        fts_matches AS (
            SELECT rowid, rank as fts_score,
            row_number() OVER (ORDER BY rank) as rank
            FROM documents_fts
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT 50
        )
        SELECT 
            kc.file_path,
            kc.content,
            (
                -- RRF Formula: 1 / (k + rank)
                COALESCE(1.0 / (60 + v.rank), 0.0) +
                COALESCE(1.0 / (60 + f.rank), 0.0)
            ) as rrf_score
        FROM knowledge_chunks kc
        LEFT JOIN vec_matches v ON kc.id = v.rowid
        LEFT JOIN fts_matches f ON kc.id = f.rowid
        WHERE v.rowid IS NOT NULL OR f.rowid IS NOT NULL
        ORDER BY rrf_score DESC
        LIMIT ?;
        """

        try:
            # Escape quotes for FTS
            fts_query = f'"{query}"' 
            rows = cursor.execute(sql, (vec_bytes, fts_query, limit)).fetchall()
        except sqlite3.OperationalError as e:
            print(f"Search Error (likely missing sqlite-vec): {e}")
            return []

        results = []
        for r in rows:
            path, content, score = r
            snippet = self._extract_snippet(content, query)
            results.append({
                "path": path,
                "score": round(score, 4),
                "snippet": snippet,
                "full_content": content # Keeping this for "Reconstruct" later
            })

        conn.close()
        return results

    def _keyword_search_only(self, cursor, query: str, limit: int) -> List[Dict]:
        """Fallback if embeddings are offline."""
        sql = """
            SELECT file_path, content
            FROM documents_fts
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        rows = cursor.execute(sql, (f'"{query}"', limit)).fetchall()
        return [{
            "path": r[0], 
            "score": 0.0, 
            "snippet": self._extract_snippet(r[1], query),
            "full_content": r[1]
        } for r in rows]

    def _get_query_embedding(self, text: str) -> Optional[List[float]]:
        """Call Ollama to get the vector for the search query."""
        try:
            res = requests.post(
                f"{OLLAMA_API_URL}/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=5
            )
            if res.status_code == 200:
                return res.json().get("embedding")
        except:
            return None
        return None

    def _extract_snippet(self, content: str, query: str) -> str:
        """Finds the best window of text around the keyword."""
        lower_content = content.lower()
        lower_query = query.lower().split()[0] # Take first word for simple centering
        
        idx = lower_content.find(lower_query)
        if idx == -1:
            return content[:200].replace('\n', ' ') + "..."
            
        start = max(0, idx - 60)
        end = min(len(content), idx + 140)
        snippet = content[start:end].replace('\n', ' ')
        return f"...{snippet}..."

# --- Independent Test Block ---
if __name__ == "__main__":
    # Note: Requires a real DB path to work
    print("Initializing Search Engine...")
    engine = SearchEngineMS()
    # Test would go here