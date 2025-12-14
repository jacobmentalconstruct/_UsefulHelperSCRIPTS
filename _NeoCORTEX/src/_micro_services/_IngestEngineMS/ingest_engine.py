import os
import time
import re
import sqlite3
import requests
import json
from typing import List, Generator, Dict, Any, Optional
from dataclasses import dataclass
from .semantic_chunker import SemanticChunker

# Optional Libraries for Enhanced Ingestion
try:
    import pypdf
except ImportError:
    pypdf = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api"

@dataclass
class IngestStatus:
    current_file: str
    progress_percent: float
    processed_files: int
    total_files: int
    log_message: str
    thought_frame: Optional[Dict] = None

class SynapseWeaver:
    """
    Parses source code to extract import dependencies.
    """
    def __init__(self):
        self.py_pattern = re.compile(r'^\s*(?:from|import)\s+([\w\.]+)')
        self.js_pattern = re.compile(r'(?:import\s+.*?from\s+[\'"]|require\([\'"])([\.\/\w\-_]+)[\'"]')

    def extract_dependencies(self, content: str, file_path: str) -> List[str]:
        dependencies = []
        # Only parse code files for dependencies
        if not file_path.endswith(('.py', '.js', '.ts', '.tsx', '.jsx')):
            return []

        lines = content.split('\n')
        for line in lines:
            match = None
            if file_path.endswith('.py'):
                match = self.py_pattern.match(line)
            else:
                match = self.js_pattern.search(line)
            
            if match:
                raw_dep = match.group(1)
                clean_dep = raw_dep.split('.')[-1].split('/')[-1]
                if clean_dep not in dependencies:
                    dependencies.append(clean_dep)
        return dependencies

class IngestEngine:
    """
    The Heavy Lifter: Reads Files (Code, PDF, MD) & Websites.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.stop_signal = False
        self.weaver = SynapseWeaver()
        self.chunker = SemanticChunker()

    def abort(self):
        self.stop_signal = True

    def check_ollama_connection(self) -> bool:
        try:
            requests.get(f"{OLLAMA_API_URL}/tags", timeout=2)
            return True
        except:
            return False

    def get_available_models(self) -> List[str]:
        try:
            res = requests.get(f"{OLLAMA_API_URL}/tags")
            if res.status_code == 200:
                data = res.json()
                return [m['name'] for m in data.get('models', [])]
        except:
            pass
        return []

    def process_files(self, file_paths: List[str], embed_model: str = "none", summary_model: str = "none") -> Generator[IngestStatus, None, None]:
        total = len(file_paths)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA synchronous = OFF")
        cursor.execute("PRAGMA journal_mode = MEMORY")

        # --- STEP 0: STAMP MANIFEST ---
        # Note: manifest table is also created during DB creation, but keep this for safety.
        cursor.execute("CREATE TABLE IF NOT EXISTS manifest (key TEXT PRIMARY KEY, value TEXT)")

        # Record the models used for this ingest in a single structured blob.
        ingest_models_obj = {"embed_model": embed_model, "summary_model": summary_model}
        cursor.execute(
            "INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)",
            ("ingest_models", json.dumps(ingest_models_obj))
        )

        # Standard run metadata
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("last_ingest_time", str(time.time())))
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("file_count", str(total)))

        # Initialize provenance if not present (do not overwrite if DB creator/UI already set it)
        cursor.execute("INSERT OR IGNORE INTO manifest (key, value) VALUES (?, ?)", ("source_provenance", "{}"))

        # Cartridge interpretation hints (do not overwrite if UI already set these)
        cursor.execute("INSERT OR IGNORE INTO manifest (key, value) VALUES (?, ?)", ("artifact_type", "unknown"))

        artifact_profile_obj = {
            "embed_model": embed_model,
            "summary_model": summary_model,
            "vfs_strategy": "relpath_from_scan_root_v1",
            "supports_graph_weaving": True,
            "notes": "artifact_type/profile may be overridden by UI in future"
        }
        cursor.execute("INSERT OR IGNORE INTO manifest (key, value) VALUES (?, ?)", ("artifact_profile", json.dumps(artifact_profile_obj)))

        conn.commit()

        node_registry = {}
        file_contents = {}

        # Compute a stable scan_root for filesystem inputs so VFS paths can be portable.
        fs_paths = [p for p in file_paths if not (p.startswith("http://") or p.startswith("https://"))]
        scan_root = ""
        if fs_paths:
            try:
                scan_root = os.path.commonpath(fs_paths)
            except Exception:
                scan_root = ""

        # Persist scan_root (do not overwrite if UI already set it)
        skeleton_tree = {}
        try:
            cursor.execute("INSERT OR IGNORE INTO manifest (key, value) VALUES (?, ?)", ("scan_root", scan_root))
            cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("vfs_strategy", "relpath_from_scan_root_v1"))
            
            # --- FEATURE: SKELETON KEY (Directory Map) ---
            # Pre-calculate the folder structure so agents can navigate without O(N) scans
            skeleton_tree = self._build_skeleton_tree(file_paths, scan_root)
            cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", 
                          ("structural_skeleton", json.dumps(skeleton_tree)))

            conn.commit()
        except Exception:
            pass

        # --- PHASE 1: INGESTION ---
        for idx, file_path in enumerate(file_paths):
            if self.stop_signal:
                yield IngestStatus(file_path, 0, idx, total, "Ingestion Aborted.")
                break

            filename = os.path.basename(file_path)
            if not filename and file_path.startswith("http"):
                filename = file_path.replace("https://", "").replace("http://", "").replace("/", "_")[:50]

            content = ""
            origin_type = 'filesystem'

            # 1. READ CONTENT (Universal Reader Logic)
            try:
                if file_path.startswith("http://") or file_path.startswith("https://"):
                    # --- WEB ---
                    origin_type = 'web'
                    yield IngestStatus(filename, (idx/total)*100, idx, total, f"Fetching URL: {file_path}...")
                    
                    resp = requests.get(file_path, timeout=10)
                    resp.raise_for_status()
                    
                    if BeautifulSoup:
                        soup = BeautifulSoup(resp.content, 'html.parser')
                        # Remove script/style
                        for script in soup(["script", "style"]): script.extract()
                        content = soup.get_text()
                    else:
                        # Fallback regex strip
                        content = re.sub('<[^<]+?>', '', resp.text)
                    
                    # Clean up whitespace
                    lines = (line.strip() for line in content.splitlines())
                    content = '\n'.join(chunk for chunk in lines if chunk)

                elif file_path.lower().endswith(".pdf"):
                    # --- PDF ---
                    if not pypdf:
                        yield IngestStatus(filename, (idx/total)*100, idx, total, "Skipping PDF (pypdf not installed)")
                        continue
                    
                    yield IngestStatus(filename, (idx/total)*100, idx, total, "Extracting PDF text...")
                    with open(file_path, 'rb') as f:
                        reader = pypdf.PdfReader(f)
                        text_pages = []
                        for page in reader.pages:
                            text_pages.append(page.extract_text())
                        content = "\n\n".join(text_pages)

                else:
                    # --- TEXT / CODE / MD ---
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

            except Exception as e:
                yield IngestStatus(filename, (idx/total)*100, idx, total, f"Read Error: {e}")
                continue

            # Derive portable VFS path + stable node_id now that origin_type is known
            if origin_type == 'web':
                vfs_path = filename
                file_key = file_path  # URLs are stable enough as identity
                node_id = file_path
                node_label = filename
            else:
                if scan_root:
                    rel = os.path.relpath(file_path, scan_root)
                    rel = rel.replace('\\', '/')
                    vfs_path = rel
                else:
                    vfs_path = filename

                file_key = vfs_path
                node_id = vfs_path
                node_label = filename

            # Cache content for weaving keyed by stable node_id
            file_contents[node_id] = content

            # 2. Summarize
            summary_text = ""
            if summary_model != "none":
                yield IngestStatus(filename, (idx/total)*100, idx, total, f"Summarizing with {summary_model}...")
                summary_text = self._generate_summary(summary_model, content[:3000])

            # 3. Track File
            try:
                meta_obj = {"summary": summary_text, "tags": []}
                meta_json = json.dumps(meta_obj)

                cursor.execute("""
                    INSERT OR REPLACE INTO files 
                    (path, content, last_updated, origin_type, origin_path, vfs_path, metadata) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (file_key, content, time.time(), origin_type, file_path, vfs_path, meta_json))
                
                file_id = cursor.lastrowid
            except sqlite3.Error as e:
                yield IngestStatus(file_path, (idx/total)*100, idx, total, f"DB Error: {e}")
                continue

            # 4. Graph Node
            node_type = 'web' if origin_type == 'web' else 'file'
            cursor.execute("""
                INSERT OR REPLACE INTO graph_nodes (id, type, label, data_json)
                VALUES (?, ?, ?, ?)
            """, (node_id, node_type, node_label, json.dumps({"origin_path": file_path, "vfs_path": vfs_path})))

            node_registry[node_id] = node_id

            # 5. Chunking & Embedding
            # Note: SemanticChunker handles generic text via _chunk_generic
            chunks = self.chunker.chunk_file(content, filename)

            for i, chunk_obj in enumerate(chunks):
                chunk_text = chunk_obj.content
                if self.stop_signal: break
                
                embedding = None
                if embed_model != "none":
                    embedding = self._get_embedding(embed_model, chunk_text)
                
                emb_blob = json.dumps(embedding).encode('utf-8') if embedding else None
                
                cursor.execute("""
                INSERT INTO chunks (file_id, chunk_index, content, embedding, name, type, start_line, end_line)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (file_id, i, chunk_text, emb_blob, chunk_obj.name, chunk_obj.type, chunk_obj.start_line, chunk_obj.end_line))

                # --- SATELLITE NODE ---
                chunk_node_id = f"{node_id}::{chunk_obj.name}"
                cursor.execute("""
                    INSERT OR REPLACE INTO graph_nodes (id, type, label, data_json)
                    VALUES (?, ?, ?, ?)
                """, (chunk_node_id, 'chunk', chunk_obj.name, json.dumps({"parent": node_id})))

                cursor.execute("""
                    INSERT OR IGNORE INTO graph_edges (source, target, weight)
                    VALUES (?, ?, 2.0)
                """, (chunk_node_id, node_id))

                # Visual Feedback
                thought_frame = {
                    "id": f"{file_id}_{i}",
                    "file": f"{filename} [{chunk_obj.name}]",
                    "chunk_index": i,
                    "content": chunk_text,
                    "vector_preview": embedding[:20] if embedding else [],
                    "concept_color": "#E02080" if origin_type == 'web' else "#007ACC"
                }
                
                yield IngestStatus(
                    current_file=filename,
                    progress_percent=((idx + (i/len(chunks))) / total) * 100,
                    processed_files=idx,
                    total_files=total,
                    log_message=f"Processing {filename}...",
                    thought_frame=thought_frame
                )

            conn.commit()

        # --- PHASE 2: WEAVING ---
        # (Only relevant for code/text files, websites typically don't have python 'imports')
        if any(f.endswith('.py') or f.endswith('.js') for f in file_paths):
            yield IngestStatus("Graph", 100, total, total, "Weaving Knowledge Graph...")
            
            for source_id, content in file_contents.items():
                if self.stop_signal: break
                deps = self.weaver.extract_dependencies(content, source_id)
                for dep in deps:
                    target_id = None
                    for potential_match in node_registry.keys():
                        base = os.path.basename(potential_match)
                        base_no_ext = os.path.splitext(base)[0]
                        if base == dep or base_no_ext == dep or potential_match.startswith(dep + '.') or potential_match == dep:
                            target_id = potential_match
                            break
                    if target_id and target_id != source_id:
                        try:
                            cursor.execute("INSERT OR IGNORE INTO graph_edges (source, target, weight) VALUES (?, ?, 1.0)", (source_id, target_id))
                        except: pass

        # --- PHASE 3: WRITE CARTRIDGE BOOT FILES (Self-Describing DB for downstream RAG) ---
        try:
            now_ts = time.time()

            # Build a lightweight inventory for INDEX.json
            ext_counts = {}
            for fp in file_paths:
                ext = os.path.splitext(fp)[1].lower() or "(none)"
                ext_counts[ext] = ext_counts.get(ext, 0) + 1

            index_obj = {
                "schema": "neocortex.cartridge.index.v1",
                "generated_at": now_ts,
                "file_count": total,
                "structural_skeleton": skeleton_tree,
                "extensions": ext_counts,
                "scan_root": scan_root,
                "vfs_strategy": "relpath_from_scan_root_v1",
                "ingest": {
                    "embed_model": embed_model,
                    "summary_model": summary_model
                },
                "graph": {
                    "dependency_edges_created": None
                },
                "boot": {
                    "readme_vfs": "__cartridge__/README.md",
                    "index_vfs": "__cartridge__/INDEX.json"
                }
            }

            readme_text = (
                "# Neural Cartridge (NeoCORTEX)\n\n"
                "This SQLite database is a *self-describing knowledge cartridge* produced by _NeoCORTEX.\n"
                "It contains ingested source material (files/pages), semantic chunks, vector embeddings, and optional graph wiring.\n\n"
                "## Boot Protocol\n"
                "- Read the manifest table first: `SELECT key, value FROM manifest`\n"
                "- Then read this file and `__cartridge__/INDEX.json` from the `files` table via `vfs_path`.\n\n"
                "## Path Contract\n"
                "- `origin_path` is provenance (absolute filesystem path or URL)\n"
                "- `vfs_path` is the cartridge-internal portable path\n"
                f"- scan_root: {scan_root}\n"
                "- vfs_strategy: relpath_from_scan_root_v1\n\n"
                "## Tables (High Level)\n"
                "- files: full source content + provenance\n"
                "- chunks: semantic segments (may include embeddings)\n"
                "- graph_nodes / graph_edges: optional structural wiring\n\n"
                "## Ingest Metadata\n"
                f"- embed_model: {embed_model}\n"
                f"- summary_model: {summary_model}\n"
                f"- file_count: {total}\n"
            )

            boot_meta_readme = json.dumps({"summary": "Cartridge boot README", "tags": ["__cartridge__", "boot", "readme"]})
            boot_meta_index = json.dumps({"summary": "Cartridge inventory index", "tags": ["__cartridge__", "boot", "index"]})

            cursor.execute(
                """
                INSERT OR REPLACE INTO files
                (path, content, last_updated, origin_type, origin_path, vfs_path, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "__cartridge__/README.md",
                    readme_text,
                    now_ts,
                    "system",
                    "__cartridge__",
                    "__cartridge__/README.md",
                    boot_meta_readme
                )
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO files
                (path, content, last_updated, origin_type, origin_path, vfs_path, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "__cartridge__/INDEX.json",
                    json.dumps(index_obj, indent=2),
                    now_ts,
                    "system",
                    "__cartridge__",
                    "__cartridge__/INDEX.json",
                    boot_meta_index
                )
            )

            cursor.execute(
                "INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)",
                ("boot_files", json.dumps(["__cartridge__/README.md", "__cartridge__/INDEX.json"]))
            )

            conn.commit()
        except Exception:
            # Never fail the ingest just because boot files couldn't be written
            pass

        conn.commit()
        conn.close()

        yield IngestStatus(
            current_file="Complete",
            progress_percent=100,
            processed_files=total,
            total_files=total,
            log_message=f"Ingestion Complete. {total} items processed. Boot files written to __cartridge__/."
        )

    def _get_embedding(self, model: str, text: str) -> Optional[List[float]]:
        try:
            res = requests.post(f"{OLLAMA_API_URL}/embeddings", json={"model": model, "prompt": text}, timeout=30)
            if res.status_code == 200: return res.json().get("embedding")
        except: return None
        return None

    def _generate_summary(self, model: str, text: str) -> str:
        try:
            prompt = f"Summarize this text in one concise sentence:\n\n{text}"
            res = requests.post(f"{OLLAMA_API_URL}/generate", json={"model": model, "prompt": prompt, "stream": False}, timeout=10)
            if res.status_code == 200: return res.json().get("response", "").strip()
        except: return ""

    def _build_skeleton_tree(self, file_paths: List[str], scan_root: str) -> Dict[str, Any]:
        """
        Constructs a lightweight directory tree (The Skeleton Key).
        Allows agents to navigate the structure without reading all files.
        """
        tree = {"_files": []}
        for fp in file_paths:
            # Mirror VFS logic from Phase 1
            if fp.startswith("http"):
                filename = fp.replace("https://", "").replace("http://", "").replace("/", "_")[:50]
                # Web pages go to root _files list for now
                tree["_files"].append(filename)
                continue

            if scan_root:
                try:
                    rel = os.path.relpath(fp, scan_root).replace('\\', '/')
                    parts = rel.split('/')
                except:
                    parts = [os.path.basename(fp)]
            else:
                parts = [os.path.basename(fp)]

            current = tree
            for i, part in enumerate(parts):
                is_file = (i == len(parts) - 1)
                if is_file:
                    if "_files" not in current: current["_files"] = []
                    current["_files"].append(part)
                else:
                    if part not in current: current[part] = {}
                    current = current[part]
        return tree

