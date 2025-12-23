import json
import re
import os
import time
import ast
import concurrent.futures
import logging
from typing import Dict, List, Any, Optional, Tuple

# Assume these are available in the local environment
try:
    from _CartridgeServiceMS import CartridgeServiceMS
    from _NeuralServiceMS import NeuralServiceMS
    from _ChunkingRouterMS import ChunkingRouterMS
except ImportError:
    # Fallbacks for static analysis or isolation
    CartridgeServiceMS = Any
    NeuralServiceMS = Any
    ChunkingRouterMS = Any

from microservice_std_lib import service_metadata, service_endpoint

logger = logging.getLogger("RefineryService")

# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="RefineryService",
    version="1.1.0",
    description="The Night Shift: Processes 'RAW' files into semantic chunks and weaves them into a knowledge graph.",
    tags=["processing", "refinery", "graph", "RAG"],
    capabilities=["smart-chunking", "graph-weaving", "parallel-embedding"]
)
class RefineryServiceMS:
    """
    The Night Shift.
    Polls the DB for 'RAW' files and processes them into Chunks and Graph Nodes.

    Graph Enrichment:
    - Code: function/class nodes, resolved import edges when possible.
    - Docs: section/chapter nodes for long-form text (md/txt/rst).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # Dependencies must be injected via config in this architecture
        self.cartridge = self.config.get("cartridge")
        self.neural = self.config.get("neural")
        
        # Instantiate internal router
        self.chunker = ChunkingRouterMS() if ChunkingRouterMS != Any else None
        
        self.start_time = time.time()
        
        # Import parsing / resolution
        self.import_pattern = re.compile(r"""(?:from|import)\s+([\w\.]+)|require\(['"]([\w\.\-/]+)['"]\)""")

        # Lightweight module/path index cache for resolving imports to VFS files
        self._module_index: Dict[str, str] = {}
        self._path_index: Dict[str, str] = {}
        self._index_built: bool = False

        # Simple section/chapter detection
        self._md_heading = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
        self._chapter_heading = re.compile(r"^\s*(chapter|CHAPTER)\s+([0-9]+|[IVXLC]+)\b\s*[:\-]?\s*(.*)$")
        
        # Initial setup if dependencies exist
        if self.cartridge and self.neural:
            self._stamp_specs()

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float", "cartridge_health": "str"},
        description="Standardized health check to verify the operational state of the Refinery service.",
        tags=["diagnostic", "health"]
    )
    def get_health(self) -> Dict[str, Any]:
        """Returns the operational status of the RefineryServiceMS."""
        cart_status = "UNKNOWN"
        if self.cartridge:
            # Assuming cartridge has a status method or dict
            cart_status = "CONNECTED" 
        
        return {
            "status": "online",
            "uptime": time.time() - self.start_time,
            "cartridge_health": cart_status
        }

    def _stamp_specs(self):
        """Writes the active Neural/Chunker configuration to the Manifest."""
        try:
            # 1. Embedding Spec
            # We assume 1024 dim for mxbai-large, but ideally we'd probe it.
            # Access config from the neural service instance
            embed_model = getattr(self.neural, "models", {}).get("embed", "default")
            
            spec = {
                "provider": "ollama",
                "model": embed_model,
                "dim": 1024,  # Hardcoded for now based on mxbai-embed-large
                "dtype": "float32",
                "distance": "cosine"
            }
            if self.cartridge:
                self.cartridge.set_manifest("embedding_spec", spec)

        except Exception as e:
            logger.error(f"Failed to stamp specs: {e}")

    def _build_import_index(self):
        """Builds caches for resolving imports to VFS targets."""
        if self._index_built or not self.cartridge:
            return

        path_index: Dict[str, str] = {}
        module_index: Dict[str, str] = {}

        conn = self.cartridge._get_conn()
        try:
            rows = conn.execute("SELECT vfs_path FROM files").fetchall()
            for (vp,) in rows:
                if not vp:
                    continue
                vfs_path = str(vp).replace("\\", "/")
                path_index[vfs_path] = vfs_path

                # Python module mapping
                if vfs_path.endswith(".py"):
                    mod = vfs_path[:-3].strip("/")
                    mod = mod.replace("/", ".")
                    if mod:
                        module_index[mod] = vfs_path

                    # If it's a package __init__.py, map the package name too
                    if vfs_path.endswith("/__init__.py"):
                        pkg = vfs_path[:-len("/__init__.py")].strip("/").replace("/", ".")
                        if pkg:
                            module_index[pkg] = vfs_path

        finally:
            conn.close()

        self._path_index = path_index
        self._module_index = module_index
        self._index_built = True

    @service_endpoint(
        inputs={"batch_size": "int"},
        outputs={"processed_count": "int"},
        description="Polls the database for files with 'RAW' status and processes them into chunks and graph nodes.",
        tags=["pipeline", "batch"],
        side_effects=["cartridge:write", "neural:inference"]
    )
    def process_pending(self, batch_size: int = 5) -> int:
        """Main loop. Returns number of files processed."""
        if not self.cartridge or not self.neural:
            logger.error("Refinery missing dependencies (Cartridge or Neural).")
            return 0

        pending = self.cartridge.get_pending_files(limit=batch_size)
        if not pending:
            return 0

        logger.info(f"Refining batch of {len(pending)} files...")

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
            # 1. Specialized Chunking via Router
            chunks = self.chunker.chunk_file(content, vfs_path)

            # 2. Vectorization & Storage
            chunk_texts = [c.content for c in chunks]

            # Buffer graph writes while DB transaction is open (prevents nested-writer locks)
            pending_nodes: List[Tuple[str, str, str, Dict[str, Any]]] = []
            pending_edges: List[Tuple[str, str, str, float]] = []

            # Use ThreadPool to embed in parallel (preserve order with map)
            max_workers = getattr(self.neural, "max_workers", 4)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                vectors = list(executor.map(self.neural.get_embedding, chunk_texts))

            conn = self.cartridge._get_conn()
            try:
                cursor = conn.cursor()

                for i, chunk in enumerate(chunks):
                    vector = vectors[i]
                    vec_blob = json.dumps(vector).encode('utf-8') if vector else None

                    # Store Chunk
                    cursor.execute(
                        """
                        INSERT INTO chunks (file_id, chunk_index, content, embedding, name, type, start_line, end_line)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (file_id, i, chunk.content, vec_blob, chunk.name, chunk.type, chunk.start_line, chunk.end_line)
                    )

                    chunk_row_id = cursor.lastrowid

                    # Insert into Vector Index (if vector exists)
                    if vector:
                        try:
                            cursor.execute(
                                "INSERT INTO vec_items(rowid, embedding) VALUES (?, ?)",
                                (chunk_row_id, json.dumps(vector))
                            )
                        except Exception as ve:
                            logger.error(f"Vector Index Insert Failed: {ve}")

                    # Graph Node for Chunks (Functions/Classes)
                    if chunk.type in ['class', 'function']:
                        node_id = f"{vfs_path}::{chunk.name}"
                        pending_nodes.append(
                            (
                                node_id,
                                'chunk',
                                chunk.name,
                                {
                                    'parent': vfs_path,
                                    'file_id': file_id,
                                    'chunk_row_id': chunk_row_id,
                                    'chunk_type': chunk.type,
                                    'start_line': chunk.start_line,
                                    'end_line': chunk.end_line
                                }
                            )
                        )
                        pending_edges.append((node_id, vfs_path, "defined_in", 1.0))

                conn.commit()

            finally:
                conn.close()

            # 3. File Level Graph Node (after close)
            pending_nodes.append((vfs_path, 'file', vfs_path.split('/')[-1], {'path': vfs_path, 'file_id': file_id}))

            # 4. Section/Chapter Weaving (docs)
            self._weave_sections(vfs_path, content)

            # 5. Import Weaving (resolved when possible)
            self._weave_imports(vfs_path, content)

            # 6. Flush buffered graph writes
            for nid, ntype, label, data in pending_nodes:
                self.cartridge.add_node(nid, ntype, label, data)
            for src, tgt, rel, w in pending_edges:
                self.cartridge.add_edge(src, tgt, rel, w)

            # 7. Mark file refined
            self.cartridge.update_status(file_id, "REFINED")

        except Exception as e:
            logger.error(f"Refining failed for {vfs_path}: {e}")
            self.cartridge.update_status(file_id, "ERROR", {"error": str(e)})

    def _extract_imports_python(self, source_path: str, content: str) -> List[Tuple[str, int, int]]:
        """Returns list of (module_or_path, level, lineno)."""
        out: List[Tuple[str, int, int]] = []
        try:
            tree = ast.parse(content)
        except Exception:
            return out

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias and alias.name:
                        out.append((alias.name, 0, getattr(node, 'lineno', 0)))
            elif isinstance(node, ast.ImportFrom):
                level = int(getattr(node, 'level', 0) or 0)
                mod = getattr(node, 'module', None) or ""
                if mod:
                    out.append((mod, level, getattr(node, 'lineno', 0)))
                else:
                    # from . import x
                    for alias in node.names:
                        if alias and alias.name:
                            out.append((alias.name, level, getattr(node, 'lineno', 0)))
        return out

    def _resolve_python_import(self, source_path: str, module: str, level: int) -> List[str]:
        """Resolve a python import to possible VFS target paths."""
        self._build_import_index()

        # Absolute: try direct module mapping
        if level <= 0:
            if module in self._module_index:
                return [self._module_index[module]]
            return []

        # Relative: resolve from the source directory
        src_dir = os.path.dirname(source_path).replace("\\", "/").strip("/")
        base_parts = src_dir.split("/") if src_dir else []

        # level=1 means "from .", so pop 0; level=2 means "from .." pop 1, etc.
        pops = max(level - 1, 0)
        if pops > 0 and pops <= len(base_parts):
            base_parts = base_parts[:-pops]

        rel_base = "/".join([p for p in base_parts if p])
        mod_path = module.replace(".", "/").strip("/")

        candidates: List[str] = []
        if rel_base:
            if mod_path:
                candidates.append(f"{rel_base}/{mod_path}.py")
                candidates.append(f"{rel_base}/{mod_path}/__init__.py")
            else:
                candidates.append(f"{rel_base}/__init__.py")
        else:
            if mod_path:
                candidates.append(f"{mod_path}.py")
                candidates.append(f"{mod_path}/__init__.py")

        return [c for c in candidates if c in self._path_index]

    def _resolve_js_like_import(self, source_path: str, imp: str) -> List[str]:
        """Resolve require('./x') / import ... from './x' to VFS candidates."""
        self._build_import_index()

        sdir = os.path.dirname(source_path).replace("\\", "/").strip("/")
        raw = imp.strip().replace("\\", "/")

        # Only try to resolve relative-ish paths
        if not (raw.startswith(".") or raw.startswith("/")):
            return []

        # Normalize
        if raw.startswith("/"):
            rel = raw.lstrip("/")
        else:
            rel = os.path.normpath(os.path.join(sdir, raw)).replace("\\", "/").lstrip("./")

        ext_candidates = [rel]
        # Common extensions
        if not os.path.splitext(rel)[1]:
            ext_candidates.extend([rel + ".js", rel + ".ts", rel + ".json"]) 
            ext_candidates.extend([rel + "/index.js", rel + "/index.ts"]) 

        return [c for c in ext_candidates if c in self._path_index]

    def _weave_imports(self, source_path: str, content: str):
        """Scans content for imports and links them in the graph."""
        targets_resolved: List[str] = []

        # Python: use AST when possible
        if source_path.endswith(".py"):
            for mod, level, lineno in self._extract_imports_python(source_path, content):
                resolved = self._resolve_python_import(source_path, mod, level)
                if resolved:
                    for tgt in resolved:
                        self.cartridge.add_edge(source_path, tgt, "imports_file", 1.0)
                        targets_resolved.append(tgt)
                else:
                    self.cartridge.add_edge(source_path, mod, "imports_unresolved", 0.25)
            return

        # JS / generic: regex fallback
        for line in content.splitlines():
            match = self.import_pattern.search(line)
            if not match:
                continue

            imp = match.group(1) or match.group(2)
            if not imp:
                continue

            resolved = self._resolve_js_like_import(source_path, imp)
            if resolved:
                for tgt in resolved:
                    self.cartridge.add_edge(source_path, tgt, "imports_file", 1.0)
                    targets_resolved.append(tgt)
            else:
                self.cartridge.add_edge(source_path, imp, "imports_unresolved", 0.25)

    def _weave_sections(self, vfs_path: str, content: str):
        """Creates section/chapter nodes for long-form text and links them to the file node."""
        ext = os.path.splitext(vfs_path)[1].lower()
        if ext not in (".md", ".markdown", ".txt", ".rst"):
            return

        lines = content.splitlines()
        for idx, line in enumerate(lines):
            lineno = idx + 1

            m = self._md_heading.match(line)
            if m:
                hashes = m.group(1)
                title = (m.group(2) or "").strip()
                level = len(hashes)
                if title:
                    node_id = f"{vfs_path}::section::{lineno}:{title}"
                    self.cartridge.add_node(node_id, "section", title, {
                        "parent": vfs_path,
                        "level": level,
                        "line": lineno
                    })
                    self.cartridge.add_edge(node_id, vfs_path, "in_file", 1.0)
                continue

            c = self._chapter_heading.match(line)
            if c:
                chap_num = (c.group(2) or "").strip()
                chap_title = (c.group(3) or "").strip()
                title = f"Chapter {chap_num}" + (f": {chap_title}" if chap_title else "")
                node_id = f"{vfs_path}::chapter::{lineno}:{chap_num}"
                self.cartridge.add_node(node_id, "section", title, {
                    "parent": vfs_path,
                    "level": 1,
                    "line": lineno
                })
                self.cartridge.add_edge(node_id, vfs_path, "in_file", 1.0)


# --- Independent Test Block ---
if __name__ == "__main__":
    # Requires Cartridge and Neural services for testing
    try:
        from _CartridgeServiceMS import CartridgeServiceMS
        from _NeuralServiceMS import NeuralServiceMS
        
        print("Initializing Dependencies...")
        c = CartridgeServiceMS({"db_path": ":memory:"})
        n = NeuralServiceMS()
        
        # Inject dependencies via config
        svc = RefineryServiceMS({"cartridge": c, "neural": n})
        print("Service ready:", svc)
        print("Health Check:", svc.get_health())
        
    except ImportError:
        print("Dependencies not found. Run in project context.")