import importlib.util
import sys
import sqlite3
import json
import struct
import requests
import os
import logging
from typing import List, Dict, Any, Optional
REQUIRED = ['requests', 'sqlite_vec']
MISSING = []
for lib in REQUIRED:
    import_name = lib.replace('-', '_')
    if importlib.util.find_spec(import_name) is None:
        MISSING.append(lib)
if MISSING:
    print('\n' + '!' * 60)
    print(f'MISSING DEPENDENCIES for _SearchEngineMS:')
    print(f"Run:  pip install {' '.join(MISSING)}")
    print('!' * 60 + '\n')
from microservice_std_lib import service_metadata, service_endpoint
DEFAULT_OLLAMA_URL = 'http://localhost:11434/api'
logger = logging.getLogger('SearchEngine')

@service_metadata(name='SearchEngine', version='1.0.0', description='The Oracle: Performs Hybrid Search (Vector Similarity + Keyword Matching) on SQLite databases.', tags=['search', 'vector', 'hybrid', 'rag'], capabilities=['db:sqlite', 'network:outbound', 'compute'], internal_dependencies=['microservice_std_lib'], external_dependencies=['requests', 'sqlite_vec'])
class SearchEngineMS:
    """
    The Oracle: Performs Hybrid Search (Vector Similarity + Keyword Matching).
    
    Architecture:
    1. Vector Search: Uses sqlite-vec (vec0) for fast nearest neighbor search.
    2. Keyword Search: Uses SQLite FTS5 for BM25-style text matching.
    3. Reranking: Combines scores using Reciprocal Rank Fusion (RRF).
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.model_name = self.config.get('model_name', 'phi3:mini-128k')
        self.ollama_url = self.config.get('ollama_url', DEFAULT_OLLAMA_URL)

    @service_endpoint(inputs={'db_path': 'str', 'query': 'str', 'limit': 'int'}, outputs={'results': 'List[Dict]'}, description='Main entry point. Returns a list of results sorted by relevance (RRF).', tags=['search', 'query'], side_effects=['db:read', 'network:outbound'])
    def search(self, db_path: str, query: str, limit: int=10) -> List[Dict[str, Any]]:
        """
        Main entry point. Returns a list of results sorted by relevance.
        """
        if not os.path.exists(db_path):
            logger.warning(f'Database not found at: {db_path}')
            return []
        conn = sqlite3.connect(db_path)
        try:
            conn.enable_load_extension(True)
            import sqlite_vec
            sqlite_vec.load(conn)
        except Exception as e:
            logger.warning(f'Warning: sqlite_vec not loaded. Vector search may fail. Error: {e}')
        cursor = conn.cursor()
        query_vec = self._get_query_embedding(query)
        if not query_vec:
            logger.info('Vectorization failed. Falling back to keyword-only search.')
            conn.close()
            return self._keyword_search_only(db_path, query, limit)
        vec_bytes = struct.pack(f'{len(query_vec)}f', *query_vec)
        sql = '\n        WITH \n        vec_matches AS (\n            SELECT rowid, distance,\n            row_number() OVER (ORDER BY distance) as rank\n            FROM knowledge_vectors\n            WHERE embedding MATCH ? \n            AND k = 50\n        ),\n        fts_matches AS (\n            SELECT rowid, rank as fts_score,\n            row_number() OVER (ORDER BY rank) as rank\n            FROM documents_fts\n            WHERE documents_fts MATCH ?\n            ORDER BY rank\n            LIMIT 50\n        )\n        SELECT \n            kc.file_path,\n            kc.content,\n            (\n                -- RRF Formula: 1 / (k + rank)\n                COALESCE(1.0 / (60 + v.rank), 0.0) +\n                COALESCE(1.0 / (60 + f.rank), 0.0)\n            ) as rrf_score\n        FROM knowledge_chunks kc\n        LEFT JOIN vec_matches v ON kc.id = v.rowid\n        LEFT JOIN fts_matches f ON kc.id = f.rowid\n        WHERE v.rowid IS NOT NULL OR f.rowid IS NOT NULL\n        ORDER BY rrf_score DESC\n        LIMIT ?;\n        '
        try:
            fts_query = f'"{query}"'
            rows = cursor.execute(sql, (vec_bytes, fts_query, limit)).fetchall()
        except sqlite3.OperationalError as e:
            logger.error(f'Search Error (likely missing schema or sqlite-vec): {e}')
            return []
        finally:
            conn.close()
        results = []
        for r in rows:
            path, content, score = r
            snippet = self._extract_snippet(content, query)
            results.append({'path': path, 'score': round(score, 4), 'snippet': snippet})
        return results

    def _keyword_search_only(self, db_path: str, query: str, limit: int) -> List[Dict[str, Any]]:
        """Fallback if embeddings are offline."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        sql = '\n            SELECT file_path, content\n            FROM documents_fts\n            WHERE documents_fts MATCH ?\n            ORDER BY rank\n            LIMIT ?\n        '
        try:
            rows = cursor.execute(sql, (f'"{query}"', limit)).fetchall()
            return [{'path': r[0], 'score': 0.0, 'snippet': self._extract_snippet(r[1], query)} for r in rows]
        except sqlite3.OperationalError as e:
            logger.error(f'Keyword Search Error: {e}')
            return []
        finally:
            conn.close()

    def _get_query_embedding(self, text: str) -> Optional[List[float]]:
        """Call Ollama to get the vector for the search query."""
        try:
            res = requests.post(f'{self.ollama_url}/embeddings', json={'model': self.model_name, 'prompt': text}, timeout=5)
            if res.status_code == 200:
                return res.json().get('embedding')
        except Exception as e:
            logger.error(f'Embedding request failed: {e}')
            return None
        return None

    def _extract_snippet(self, content: str, query: str) -> str:
        """Finds the best window of text around the keyword."""
        if not content:
            return ''
        lower_content = content.lower()
        parts = query.lower().split()
        lower_query = parts[0] if parts else ''
        idx = lower_content.find(lower_query)
        if idx == -1:
            return content[:200].replace('\n', ' ') + '...'
        start = max(0, idx - 60)
        end = min(len(content), idx + 140)
        snippet = content[start:end].replace('\n', ' ')
        return f'...{snippet}...'
if __name__ == '__main__':
    print('Initializing Search Engine...')
    engine = SearchEngineMS({'model_name': 'phi3:mini-128k'})
    print('Service ready:', engine)
