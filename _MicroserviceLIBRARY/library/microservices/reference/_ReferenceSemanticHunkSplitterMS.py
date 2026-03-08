import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_endpoint, service_metadata


DEFAULT_SEMANTIC_HUNKS = [
    "class TreeItem:",
    "class BaseCurationTool(ABC):",
    "class ViewerPanel(tk.Frame):",
    "class ViewerStack(tk.Frame):",
    "class TripartiteDataStore:",
    "def _build_workspace(self):",
    "def _patch_validate(self):",
    "def _run_ingest(self, source_path: str):",
    "def _query_semantic_layer(self, query: str, top_k: int):",
]


@service_metadata(
    name="ReferenceSemanticHunkSplitterMS",
    version="1.0.0",
    description="Pilfered from file_splitter.py. Provides semantic anchor splitting for large Python files with optional write-out.",
    tags=["chunking", "splitter", "refactor"],
    capabilities=["filesystem:read", "filesystem:write", "compute"],
    side_effects=["filesystem:read", "filesystem:write"],
    internal_dependencies=["microservice_std_lib"],
    external_dependencies=[],
)
class ReferenceSemanticHunkSplitterMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(
        inputs={},
        outputs={"hunks": "list[str]"},
        description="Return default semantic anchor list used for datastore splitting.",
        tags=["splitter", "defaults"],
    )
    def get_default_hunks(self) -> List[str]:
        return list(DEFAULT_SEMANTIC_HUNKS)

    @service_endpoint(
        inputs={"lines": "list[str]", "hunks": "list[str]|None"},
        outputs={"analysis": "dict"},
        description="Find split indices from semantic anchor starts, including ambiguous matches.",
        tags=["splitter", "analysis"],
    )
    def find_split_indices(self, lines: List[str], hunks: Optional[List[str]] = None) -> Dict[str, Any]:
        anchors = hunks or DEFAULT_SEMANTIC_HUNKS
        split_indices = [0]
        ambiguous: Dict[str, int] = {}
        missing: List[str] = []

        for hunk in anchors:
            matches = [i for i, line in enumerate(lines) if line.strip().startswith(hunk)]
            if len(matches) == 1:
                split_indices.append(matches[0])
            elif len(matches) > 1:
                ambiguous[hunk] = len(matches)
            else:
                missing.append(hunk)

        split_indices.append(len(lines))
        split_indices = sorted(set(split_indices))
        return {
            "split_indices": split_indices,
            "ambiguous": ambiguous,
            "missing": missing,
            "segments": max(0, len(split_indices) - 1),
        }

    @service_endpoint(
        inputs={"text": "str", "hunks": "list[str]|None"},
        outputs={"result": "dict"},
        description="Split in-memory text into semantic chunks with index metadata.",
        tags=["splitter", "chunking"],
    )
    def split_text(self, text: str, hunks: Optional[List[str]] = None) -> Dict[str, Any]:
        lines = text.splitlines(keepends=True)
        analysis = self.find_split_indices(lines, hunks=hunks)
        indices = analysis["split_indices"]

        chunks: List[Dict[str, Any]] = []
        for i in range(len(indices) - 1):
            start = indices[i]
            end = indices[i + 1]
            chunk_text = "".join(lines[start:end])
            chunks.append({
                "index": i,
                "line_start": start,
                "line_end": max(start, end - 1),
                "text": chunk_text,
            })

        return {
            "chunks": chunks,
            "analysis": analysis,
        }

    @service_endpoint(
        inputs={"file_name": "str", "segment_count": "int"},
        outputs={"names": "list[str]"},
        description="Build deterministic output names using _hunk_## suffix pattern.",
        tags=["splitter", "naming"],
    )
    def build_output_names(self, file_name: str, segment_count: int) -> List[str]:
        p = Path(file_name)
        stem = p.stem
        suffix = p.suffix
        return [f"{stem}_hunk_{i:02d}{suffix}" for i in range(max(0, int(segment_count)))]

    @service_endpoint(
        inputs={"file_path": "str", "hunks": "list[str]|None"},
        outputs={"result": "dict"},
        description="Read a file and return semantic split analysis plus chunk payloads.",
        tags=["splitter", "filesystem"],
        side_effects=["filesystem:read"],
    )
    def split_file_preview(self, file_path: str, hunks: Optional[List[str]] = None) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            return {"ok": False, "error": "file_not_found", "path": str(path)}
        text = path.read_text(encoding="utf-8", errors="ignore")
        result = self.split_text(text, hunks=hunks)
        return {"ok": True, "path": str(path), **result}

    @service_endpoint(
        inputs={"file_path": "str", "output_dir": "str|None", "hunks": "list[str]|None"},
        outputs={"result": "dict"},
        description="Split file by semantic hunks and write chunk files to output directory (or source directory).",
        tags=["splitter", "filesystem", "write"],
        side_effects=["filesystem:read", "filesystem:write"],
    )
    def split_file_to_disk(self, file_path: str, output_dir: Optional[str] = None, hunks: Optional[List[str]] = None) -> Dict[str, Any]:
        preview = self.split_file_preview(file_path, hunks=hunks)
        if not preview.get("ok"):
            return preview

        path = Path(file_path)
        out_dir = Path(output_dir) if output_dir else path.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        chunks = preview["chunks"]
        names = self.build_output_names(path.name, len(chunks))

        written: List[str] = []
        for chunk, name in zip(chunks, names):
            out_path = out_dir / name
            out_path.write_text(chunk["text"], encoding="utf-8")
            written.append(str(out_path))

        return {
            "ok": True,
            "source": str(path),
            "output_dir": str(out_dir),
            "files_written": written,
            "analysis": preview["analysis"],
        }

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float"},
        description="Standardized health check for service status.",
        tags=["diagnostic", "health"],
    )
    def get_health(self):
        return {"status": "online", "uptime": time.time() - self.start_time}