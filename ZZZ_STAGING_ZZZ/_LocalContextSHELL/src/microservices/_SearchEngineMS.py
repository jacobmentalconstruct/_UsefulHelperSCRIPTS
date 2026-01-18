import importlib.util
import sys
import sqlite3
import json
import struct
import requests
import os
import logging
from typing import List, Dict, Any, Optional

# --- RUNTIME DEPENDENCY CHECK ---
REQUIRED = ["requests", "sqlite_vec"] # 'sqlite-vec' package name is often 'sqlite_vec' in pip/import
MISSING = []

for lib in REQUIRED:
    # Handle hyphenated package names for import check vs pip name
    import_name = lib.replace("-", "_")
    if importlib.util.find_spec(import_name) is None:
        MISSING.append(lib)

if MISSING:
    print('\n' + '!'*60)
    print(f'MISSING DEPENDENCIES for _SearchEngineMS:')
    print(f'Run:  pip install {" ".join(MISSING)}')
    print('!'*60 + '\n')
    # We proceed so the class loads, but methods will likely fail.

from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION
# ==============================================================================

DEFAULT_OLLAMA_URL = "http://localhost:11434/api"
logger = logging.getLogger("SearchEngine")

# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="SearchEngine",
    version="1.0.0",
    description="The Oracle: Performs Hybrid Search (Vector Similarity + Keyword Matching) on SQLite databases.",
    tags=["search", "vector", "hybrid", "rag"],
    capabilities=["db:sqlite", "network:outbound", "compute"]
)
class SearchEngineMS:
    """
    The Oracle: Performs Hybrid Search (Vector Similarity + Keyword Matching).
    
    Architecture:
    1. Vector Search: Uses sqlite-vec (vec0) for fast nearest neighbor search.
    2. Keyword Search: Uses SQLite FTS5 for BM25-style text matching.
    3. Reranking: Combines scores using Reciprocal Rank Fusion (RRF).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.model_name = self.config.get("model_name", "phi3:mini-128k")
        self.ollama_url = self.config.get("ollama_url", DEFAULT_OLLAMA_URL)

    @service_endpoint(
        inputs={"db_path": "str", "query": "str", "limit": "int"},
        outputs={"results": "List[Dict]"},
        description="Main entry point. Returns a list of results.",
        tags=["search", "query"],
        side_effects=["db:read", "network:outbound"]
    )
    def search(self, db_path: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Smart Keyword Search (Patch).
        Splits query into keywords and searches both Content and Filenames.
        """
        if not os.path.exists(db_path):
            logger.warning(f"Database not found at: {db_path}")
            return []

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Break query into keywords (e.g., "What is app.py" -> ["app.py"])
        # We ignore short words to reduce noise
        words = query.split()
        keywords = [w for w in words if len(w) > 2]
        
        # Fallback: if all words are short, use the whole query
        if not keywords:
            keywords = [query]

        # 2. Build Dynamic SQL (Search Content OR Filename)
        conditions = []
        params = []
        
        for w in keywords:
            # Check if the word is in the file content
            conditions.append("c.content LIKE ?")
            params.append(f"%{w}%")
            # Check if the word is in the filename (e.g. searching for "app")
            conditions.append("f.path LIKE ?")
            params.append(f"%{w}%")
            
        where_clause = " OR ".join(conditions)
        
        # We join 'chunks' with 'files' to get the path
        sql = f"""
        SELECT DISTINCT
            f.path as file_path,
            c.content,
            1.0 as score
        FROM chunks c
        JOIN files f ON c.file_id = f.id
        WHERE {where_clause}
        LIMIT ?
        """
        
        # Add limit to params
        params.append(limit)

        try:
            rows = cursor.execute(sql, params).fetchall()
        except sqlite3.OperationalError as e:
            logger.error(f"Search Error: {e}")
            return []
        finally:
            conn.close()

        results = []
        for r in rows:
            path = r["file_path"]
            content = r["content"]
            score = r["score"]
            
            snippet = self._extract_snippet(content, query)
            results.append({
                "path": path,
                "score": round(score, 4),
                "snippet": snippet
            })

        return results
    def search(self, db_path: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Smart Keyword Search (Patch).
        Splits query into keywords and searches both Content and Filenames.
        """
        if not os.path.exists(db_path):
            logger.warning(f"Database not found at: {db_path}")
            return []

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Break query into keywords (e.g., "What is app.py" -> ["app.py"])
        # We ignore short words to reduce noise
        words = query.split()
        keywords = [w for w in words if len(w) > 2]
        
        # Fallback: if all words are short, use the whole query
        if not keywords:
            keywords = [query]

        # 2. Build Dynamic SQL (Search Content OR Filename)
        conditions = []
        params = []
        
        for w in keywords:
            # Check if the word is in the file content
            conditions.append("c.content LIKE ?")
            params.append(f"%{w}%")
            # Check if the word is in the filename (vfs_path is the portable path column)
            conditions.append("f.vfs_path LIKE ?")
            params.append(f"%{w}%")
            
        where_clause = " OR ".join(conditions)
        
        # We join 'chunks' with 'files' to get the vfs_path
        sql = f"""
        SELECT DISTINCT
            f.vfs_path as file_path,
            c.content,
            1.0 as score
        FROM chunks c
        JOIN files f ON c.file_id = f.id
        WHERE {where_clause}
        LIMIT ?
        """
        
        # Add limit to params
        params.append(limit)

        try:
            rows = cursor.execute(sql, params).fetchall()
        except sqlite3.OperationalError as e:
            logger.error(f"Search Error: {e}")
            return []
        finally:
            conn.close()

        results = []
        for r in rows:
            path = r["file_path"]
            content = r["content"]
            score = r["score"]
            
            snippet = self._extract_snippet(content, query)
            results.append({
                "path": path,
                "score": round(score, 4),
                "snippet": snippet
            })

        return results

        """
        Patched entry point. 
        Targets the actual 'chunks' and 'files' tables created by IngestEngine.
        """
        if not os.path.exists(db_path):
            logger.warning(f"Database not found at: {db_path}")
            return []

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # We will perform a basic similarity search using LIKE since FTS/Vector tables
        # aren't populated by the current IngestEngine.
        # Ideally, we would rely on vector search, but let's get data flowing first.
        
        sql = """
        SELECT 
            f.path as file_path,
            c.content,
            0.9 as score -- Dummy score since we aren't using RRF yet
        FROM chunks c
        JOIN files f ON c.file_id = f.id
        WHERE c.content LIKE ?
        LIMIT ?
        """

        try:
            # Simple keyword match
            search_term = f"%{query}%"
            rows = cursor.execute(sql, (search_term, limit)).fetchall()
        except sqlite3.OperationalError as e:
            logger.error(f"Search Error: {e}")
            return []
        finally:
            conn.close()

        results = []
        for r in rows:
            path = r["file_path"]
            content = r["content"]
            score = r["score"]
            
            snippet = self._extract_snippet(content, query)
            results.append({
                "path": path,
                "score": round(score, 4),
                "snippet": snippet
            })

        return results

        conn = sqlite3.connect(db_path)
        # Enable sqlite-vec extension
        try:
            conn.enable_load_extension(True)
            import sqlite_vec
            sqlite_vec.load(conn)
        except Exception as e:
            logger.warning(f"Warning: sqlite_vec not loaded. Vector search may fail. Error: {e}")

        cursor = conn.cursor()

        # 1. Vectorize the User Query
        query_vec = self._get_query_embedding(query)
        if not query_vec:
            # Fallback to keyword only if embedding fails
            logger.info("Vectorization failed. Falling back to keyword-only search.")
            conn.close()
            # Re-open connection is not strictly necessary for fallback logic, 
            # but we return early. Note: _keyword_search_only expects a cursor.
            # We reopen/reuse properly:
            return self._keyword_search_only(db_path, query, limit)

        # Pack vector for sqlite-vec (Float32 Little Endian)
        vec_bytes = struct.pack(f'{len(query_vec)}f', *query_vec)

        # 2. HYBRID QUERY (The "Magic" SQL)
        # Note: This SQL assumes a specific schema ('knowledge_vectors', 'documents_fts', 'knowledge_chunks').
        # Ensure your database setup (e.g. Refinery/Librarian) matches these table names.
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
            logger.error(f"Search Error (likely missing schema or sqlite-vec): {e}")
            return []
        finally:
            conn.close()

        results = []
        for r in rows:
            path, content, score = r
            snippet = self._extract_snippet(content, query)
            results.append({
                "path": path,
                "score": round(score, 4),
                "snippet": snippet,
                # "full_content": content # Optional: Uncomment if full content is needed
            })

        return results

    def _keyword_search_only(self, db_path: str, query: str, limit: int) -> List[Dict[str, Any]]:
        """Fallback if embeddings are offline."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        sql = """
            SELECT file_path, content
            FROM documents_fts
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        try:
            rows = cursor.execute(sql, (f'"{query}"', limit)).fetchall()
            return [{
                "path": r[0], 
                "score": 0.0, 
                "snippet": self._extract_snippet(r[1], query)
            } for r in rows]
        except sqlite3.OperationalError as e:
            logger.error(f"Keyword Search Error: {e}")
            return []
        finally:
            conn.close()

    def _get_query_embedding(self, text: str) -> Optional[List[float]]:
        """Call Ollama to get the vector for the search query."""
        try:
            res = requests.post(
                f"{self.ollama_url}/embeddings",
                json={"model": self.model_name, "prompt": text},
                timeout=5
            )
            if res.status_code == 200:
                return res.json().get("embedding")
        except Exception as e:
            logger.error(f"Embedding request failed: {e}")
            return None
        return None

    def _extract_snippet(self, content: str, query: str) -> str:
        """Finds the best window of text around the keyword."""
        if not content:
            return ""
            
        lower_content = content.lower()
        parts = query.lower().split()
        lower_query = parts[0] if parts else "" 
        
        idx = lower_content.find(lower_query)
        if idx == -1:
            return content[:200].replace('\n', ' ') + "..."
            
        start = max(0, idx - 60)
        end = min(len(content), idx + 140)
        snippet = content[start:end].replace('\n', ' ')
        return f"...{snippet}..."


# --- Independent Test Block ---
if __name__ == "__main__":
    # Note: Requires a real DB path to work effectively
    print("Initializing Search Engine...")
    engine = SearchEngineMS({"model_name": "phi3:mini-128k"})
    print("Service ready:", engine)
    
    # Example usage:
    # results = engine.search("my_knowledge.db", "python error handling")
    # print(results)
