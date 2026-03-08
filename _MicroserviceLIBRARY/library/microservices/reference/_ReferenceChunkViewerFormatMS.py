import time
from typing import Any, Dict, List

from microservice_std_lib import service_endpoint, service_metadata


TYPE_COLOURS = {
    "function_def": "#5de4c7",
    "method_def": "#5de4c7",
    "class_def": "#7c6af7",
    "module_summary": "#a6e3a1",
    "import_block": "#6e6c8e",
    "document_summary": "#a6e3a1",
    "document": "#a6e3a1",
    "section": "#89dceb",
    "subsection": "#89dceb",
    "paragraph": "#cdd6f4",
    "generic": "#6e6c8e",
}

PREVIEW_LINES = 12
DIVIDER_WIDTH = 62


def _thick_divider(chunk_type: str, width: int = DIVIDER_WIDTH) -> str:
    label = f" {chunk_type} "
    pad = "=" * max(2, (width - len(label)) // 2)
    return f"{pad}{label}{pad}"


@service_metadata(
    name="ReferenceChunkViewerFormatMS",
    version="1.0.0",
    description="Pilfered from chunk_viewer.py. Formats chunk stream blocks for logs or headless UI rendering.",
    tags=["viewer", "chunking", "formatting"],
    capabilities=["compute"],
    side_effects=[],
    internal_dependencies=["microservice_std_lib"],
    external_dependencies=[],
)
class ReferenceChunkViewerFormatMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(
        inputs={"chunk_type": "str"},
        outputs={"color": "str"},
        description="Map chunk type to display colour token.",
        tags=["viewer", "style"],
    )
    def type_colour(self, chunk_type: str) -> str:
        return TYPE_COLOURS.get(chunk_type, "#cdd6f4")

    @service_endpoint(
        inputs={"chunk_type": "str", "width": "int"},
        outputs={"divider": "str"},
        description="Build thick top divider with centered chunk type label.",
        tags=["viewer", "format"],
    )
    def top_divider(self, chunk_type: str, width: int = DIVIDER_WIDTH) -> str:
        return _thick_divider(chunk_type, width=width)

    @service_endpoint(
        inputs={"width": "int"},
        outputs={"divider": "str"},
        description="Build thin separator divider.",
        tags=["viewer", "format"],
    )
    def thin_divider(self, width: int = DIVIDER_WIDTH) -> str:
        return "-" * max(8, int(width))

    @service_endpoint(
        inputs={"width": "int"},
        outputs={"divider": "str"},
        description="Build bottom block divider.",
        tags=["viewer", "format"],
    )
    def bottom_divider(self, width: int = DIVIDER_WIDTH) -> str:
        return "=" * max(8, int(width))

    @service_endpoint(
        inputs={"line_start": "int", "line_end": "int", "tokens": "int", "index": "int", "total": "int"},
        outputs={"meta": "str"},
        description="Format canonical metadata line for chunk blocks.",
        tags=["viewer", "format"],
    )
    def meta_line(self, line_start: int, line_end: int, tokens: int, index: int, total: int) -> str:
        return f"  lines {line_start}-{line_end}  |  {tokens} tokens  |  chunk {index + 1} of {total}"

    @service_endpoint(
        inputs={"text": "str", "max_preview_lines": "int"},
        outputs={"preview": "dict"},
        description="Create preview text and truncation metadata for chunk display.",
        tags=["viewer", "preview"],
    )
    def preview_text(self, text: str, max_preview_lines: int = PREVIEW_LINES) -> Dict[str, Any]:
        lines = text.splitlines()
        limit = max(1, int(max_preview_lines))
        if len(lines) <= limit:
            return {"text": text, "truncated": False, "remaining_lines": 0}

        preview = "\n".join(lines[:limit])
        remaining = len(lines) - limit
        tail = f"\n  ... {remaining} more line{'s' if remaining != 1 else ''}"
        return {
            "text": preview + tail,
            "truncated": True,
            "remaining_lines": remaining,
        }

    @service_endpoint(
        inputs={
            "chunk_type": "str",
            "context_prefix": "str",
            "text": "str",
            "line_start": "int",
            "line_end": "int",
            "tokens": "int",
            "index": "int",
            "total": "int",
            "max_preview_lines": "int",
        },
        outputs={"block": "dict"},
        description="Render a complete chunk block payload with both plain-text and structured sections.",
        tags=["viewer", "format", "chunk"],
    )
    def render_chunk_block(
        self,
        chunk_type: str,
        context_prefix: str,
        text: str,
        line_start: int,
        line_end: int,
        tokens: int,
        index: int,
        total: int,
        max_preview_lines: int = PREVIEW_LINES,
    ) -> Dict[str, Any]:
        top = self.top_divider(chunk_type)
        meta = self.meta_line(line_start, line_end, tokens, index, total)
        preview = self.preview_text(text, max_preview_lines=max_preview_lines)
        mid = self.thin_divider()
        bottom = self.bottom_divider()

        lines: List[str] = [top]
        if context_prefix:
            lines.append(f"  {context_prefix}")
        lines.append(meta)
        lines.append(mid)
        lines.append(preview["text"])
        lines.append(bottom)

        return {
            "chunk_type": chunk_type,
            "color": self.type_colour(chunk_type),
            "text_block": "\n".join(lines),
            "truncated": bool(preview["truncated"]),
            "remaining_lines": int(preview["remaining_lines"]),
        }

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float"},
        description="Standardized health check for service status.",
        tags=["diagnostic", "health"],
    )
    def get_health(self):
        return {"status": "online", "uptime": time.time() - self.start_time}