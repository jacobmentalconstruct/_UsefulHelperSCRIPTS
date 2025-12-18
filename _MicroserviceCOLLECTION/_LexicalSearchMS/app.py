import sqlite3
import json
import os
from typing import List, Dict, Any, Optional
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
name="LexicalSearch",
version="1.0.0",
description="Lightweight BM25 keyword search using SQLite FTS5 (No AI required).",
tags=["search", "index", "sqlite"],
capabilities=["db:sqlite", "filesystem:read", "filesystem:write"]
)
class LexicalSearchMS:
    """
The Librarian's Index: A lightweight, AI-free search engine.
    
Uses SQLite's FTS5 extension to provide fast, ranked keyword search (BM25).
Ideal for environments where installing PyTorch/Transformers is impossible
or overkill.
"""

def __init__(self, config: Optional[Dict[str, Any]] = None):
self.config = config or {}
default_db = str(Path(__file__).parent / "lexical_index.db")
self.db_path = self.config.get("db_path", default_db)
self._init_db()

    def _init_db(self):
        """
        Sets up the schema. 
        Uses Triggers to automatically keep the FTS index in sync with the main table.
        """
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # 1. Main Content Table (Stores the actual data)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                content TEXT,
                metadata TEXT  -- JSON blob for extra info (path, author, etc)
            );
        """)
        
        # 2. Virtual FTS Table (The Search Index)
        # content='documents' means it references the table above (saves space)
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                content,
                content='documents',
                content_rowid='rowid'  -- Internal SQLite mapping
            );
        """)

        # 3. Triggers (The "Magic" - Auto-sync index on Insert/Delete/Update)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS doc_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
        """)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS doc_ad AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, content) VALUES('delete', old.rowid, old.content);
            END;
        """)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS doc_au AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, content) VALUES('delete', old.rowid, old.content);
                INSERT INTO documents_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
        """)
        
        conn.commit()
        conn.close()

    @service_endpoint(
    inputs={"doc_id": "str", "text": "str", "metadata": "Dict"},
    outputs={},
    description="Adds or updates a document in the FTS index.",
    tags=["search", "write"],
    side_effects=["db:write"]
    )
    def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any] = None):
    """
    Adds or updates a document in the index.
    """
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        meta_json = json.dumps(metadata or {})
        
        # Upsert logic (Replace if ID exists)
        cur.execute("""
            INSERT OR REPLACE INTO documents (id, content, metadata)
            VALUES (?, ?, ?)
        """, (doc_id, text, meta_json))
        
        conn.commit()
        conn.close()

    @service_endpoint(
    inputs={"query": "str", "top_k": "int"},
    outputs={"results": "List[Dict]"},
    description="Performs a BM25 ranked keyword search.",
    tags=["search", "read"],
    side_effects=["db:read"]
    )
    def search(self, query: str, top_k: int = 20) -> List[Dict]:
    """
    Performs a BM25 Ranked Search.
    """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # Allows dict-like access
        cur = conn.cursor()
        
        try:
            # The SQL Magic: 'bm25(documents_fts)' calculates relevance score
            sql = """
                SELECT 
                    d.id, 
                    d.content, 
                    d.metadata,
                    snippet(documents_fts, 0, '<b>', '</b>', '...', 15) as preview,
                    bm25(documents_fts) as score
                FROM documents_fts 
                JOIN documents d ON d.rowid = documents_fts.rowid
                WHERE documents_fts MATCH ? 
                ORDER BY score ASC
                LIMIT ?
            """
            # FTS5 query syntax: quotes typically help with special chars
            safe_query = f'"{query}"'
            rows = cur.execute(sql, (safe_query, top_k)).fetchall()
            
            results = []
            for r in rows:
                results.append({
                    "id": r['id'],
                    "score": round(r['score'], 4),
                    "preview": r['preview'], # FTS5 auto-generates snippets!
                    "metadata": json.loads(r['metadata']),
                    "full_content": r['content']
                })
            
            return results
            
        except sqlite3.OperationalError as e:
            # Usually happens if query syntax is bad (e.g. unmatched quotes)
            print(f"Search syntax error: {e}")
            return []
        finally:
            conn.close()

# --- Independent Test Block ---
if __name__ == "__main__":
    import os
    
    db_name = "test_lexical.db"
    
    # 1. Init
    engine = LexicalSearchMS({"db_path": db_name})
    print("Service ready:", engine)
    
    # 2. Ingest Data
    print("Ingesting test data...")
    engine.add_document("doc1", "Python is a great language for data science.", {"category": "coding"})
    engine.add_document("doc2", "The snake python is a reptile found in jungles.", {"category": "biology"})
    engine.add_document("doc3", "Data science involves python, pandas, and SQL.", {"category": "coding"})
    
# 3. Search
query = "python data"
print(f"\nSearching for: '{query}'")
hits = engine.search(query)
    
for hit in hits:
    print(f"[{hit['score']:.4f}] {hit['id']} ({hit['metadata']['category']})")
    print(f"   Preview: {hit['preview']}")
        
# Cleanup
if os.path.exists(db_name):
    os.remove(db_name)
