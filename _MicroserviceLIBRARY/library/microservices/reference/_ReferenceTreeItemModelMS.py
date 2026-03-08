import time
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_endpoint, service_metadata


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@service_metadata(
    name="ReferenceTreeItemModelMS",
    version="1.0.0",
    description="Pilfered from models/tree_item.py. Normalizes tree-item records and provides hierarchy/flatten helpers.",
    tags=["tree", "model", "explorer"],
    capabilities=["compute"],
    side_effects=[],
    internal_dependencies=["microservice_std_lib"],
    external_dependencies=[],
)
class ReferenceTreeItemModelMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(
        inputs={"row": "dict"},
        outputs={"item": "dict"},
        description="Normalize a raw row into a canonical TreeItem-like dictionary shape.",
        tags=["tree", "normalize"],
    )
    def coerce_tree_item(self, row: Dict[str, Any]) -> Dict[str, Any]:
        item = {
            "node_id": str(row.get("node_id", "")),
            "node_type": str(row.get("node_type", "unknown")),
            "name": str(row.get("name", "")),
            "parent_id": row.get("parent_id"),
            "path": str(row.get("path", "")),
            "depth": _coerce_int(row.get("depth", 0)),
            "file_cid": row.get("file_cid"),
            "line_start": row.get("line_start"),
            "line_end": row.get("line_end"),
            "language_tier": str(row.get("language_tier", "unknown")),
            "chunk_id": row.get("chunk_id"),
            "token_count": _coerce_int(row.get("token_count", 0)),
            "embed_status": str(row.get("embed_status", "")),
            "semantic_depth": _coerce_int(row.get("semantic_depth", 0)),
            "structural_depth": _coerce_int(row.get("structural_depth", 0)),
            "context_prefix": str(row.get("context_prefix", "")),
            "children": list(row.get("children", [])),
        }
        return item

    @service_endpoint(
        inputs={"rows": "list"},
        outputs={"roots": "list"},
        description="Build parent/child hierarchy from flat tree-item rows.",
        tags=["tree", "hierarchy"],
    )
    def build_hierarchy(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = self.coerce_tree_item(row)
            if item["node_id"]:
                items[item["node_id"]] = item

        roots: List[Dict[str, Any]] = []
        for item in items.values():
            parent_id = item.get("parent_id")
            if parent_id and parent_id in items:
                items[parent_id].setdefault("children", []).append(item)
            else:
                roots.append(item)

        self._sort_recursive(roots)
        return roots

    def _sort_recursive(self, nodes: List[Dict[str, Any]]) -> None:
        def _key(n: Dict[str, Any]):
            return (
                n.get("node_type") != "directory",
                n.get("node_type") != "virtual_file",
                n.get("node_type") != "file",
                _coerce_int(n.get("line_start"), 9_999_999),
                str(n.get("name", "")).lower(),
            )

        nodes.sort(key=_key)
        for node in nodes:
            children = node.get("children", [])
            if children:
                self._sort_recursive(children)

    @service_endpoint(
        inputs={"roots": "list"},
        outputs={"rows": "list"},
        description="Flatten hierarchy into pre-order row list for export or indexing.",
        tags=["tree", "flatten"],
    )
    def flatten_hierarchy(self, roots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        def walk(nodes: List[Dict[str, Any]]):
            for node in nodes:
                clean = dict(node)
                children = clean.pop("children", [])
                out.append(clean)
                walk(children)

        walk(roots)
        return out

    @service_endpoint(
        inputs={"roots": "list"},
        outputs={"summary": "dict"},
        description="Summarize tree counts by node type and language tier.",
        tags=["tree", "stats"],
    )
    def summarize_hierarchy(self, roots: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary = {
            "total": 0,
            "by_node_type": {},
            "by_language_tier": {},
            "max_depth": 0,
        }

        def walk(nodes: List[Dict[str, Any]]):
            for node in nodes:
                summary["total"] += 1
                ntype = str(node.get("node_type", "unknown"))
                tier = str(node.get("language_tier", "unknown"))
                depth = _coerce_int(node.get("depth", 0))
                summary["by_node_type"][ntype] = summary["by_node_type"].get(ntype, 0) + 1
                summary["by_language_tier"][tier] = summary["by_language_tier"].get(tier, 0) + 1
                if depth > summary["max_depth"]:
                    summary["max_depth"] = depth
                walk(node.get("children", []))

        walk(roots)
        return summary

    @service_endpoint(
        inputs={"rows": "list", "node_id": "str"},
        outputs={"item": "dict|None"},
        description="Find a single normalized item by node_id from row list.",
        tags=["tree", "lookup"],
    )
    def find_by_node_id(self, rows: List[Dict[str, Any]], node_id: str) -> Optional[Dict[str, Any]]:
        target = node_id.strip()
        for row in rows:
            item = self.coerce_tree_item(row)
            if item["node_id"] == target:
                return item
        return None

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float"},
        description="Standardized health check for service status.",
        tags=["diagnostic", "health"],
    )
    def get_health(self):
        return {"status": "online", "uptime": time.time() - self.start_time}