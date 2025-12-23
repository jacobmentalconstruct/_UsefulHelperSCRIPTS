"""
SERVICE_NAME: _CodeGrapherMS
ENTRY_POINT: _CodeGrapherMS.py
DEPENDENCIES: None
"""

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_metadata, service_endpoint, BaseService

# ==============================================================================
# HELPER: AST VISITOR
# ==============================================================================
class SurgicalVisitor(ast.NodeVisitor):
    """
    Extracts function definitions, calls, and class structures from AST.
    """
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.symbols = []

    def visit_FunctionDef(self, node):
        self._handle_func(node, "function")

    def visit_AsyncFunctionDef(self, node):
        self._handle_func(node, "async_function")

    def visit_ClassDef(self, node):
        # Record the class
        class_id = f"{self.file_path}::{node.name}"
        self.symbols.append({
            "id": class_id,
            "file": self.file_path,
            "name": node.name,
            "type": "class",
            "line": node.lineno,
            "calls": [] # Classes don't 'call' things directly usually, their methods do
        })
        # Visit children (methods)
        self.generic_visit(node)

    def _handle_func(self, node, type_name):
        # Extract outgoing calls from the function body
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        
        unique_calls = list(set(calls))
        
        node_id = f"{self.file_path}::{node.name}"
        self.symbols.append({
            "id": node_id,
            "file": self.file_path,
            "name": node.name,
            "type": type_name,
            "line": node.lineno,
            "calls": unique_calls
        })

# ==============================================================================
# SERVICE DEFINITION
# ==============================================================================
@service_metadata(
    name="CodeGrapher",
    version="1.0.0",
    description="Parses Python code to extract symbols (nodes) and call relationships (edges).",
    tags=["parsing", "graph", "analysis"],
    capabilities=["filesystem:read"],
    dependencies=["ast", "pathlib"],
    side_effects=["filesystem:read"]
)
class CodeGrapherMS(BaseService):
    """
    The Cartographer of Logic: Parses Python code to extract high-level 
    symbols (classes, functions) and maps their 'Call' relationships.
    
    Output: A graph structure (Nodes + Edges) suitable for visualization 
    or dependency analysis.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("CodeGrapher")
        self.config = config or {}
        self.nodes = [] # List of symbols (functions, classes)
        self.edges = [] # List of relationships (source -> target)

    @service_endpoint(
        inputs={"root_path": "str"},
        outputs={"graph_data": "Dict[str, Any]"},
        description="Recursively scans a directory for .py files and builds the graph.",
        tags=["parsing", "graph"],
        side_effects=["filesystem:read"]
    )
    def scan_directory(self, root_path: str) -> Dict[str, Any]:
        """
        Recursively scans a directory for .py files and builds the graph.
        """
        root = Path(root_path).resolve()
        self.nodes = []
        self.edges = []
        
        if not root.exists():
            return {"error": f"Path {root} does not exist"}

        # 1. Parsing Pass (Create Nodes)
        for path in root.rglob("*.py"):
            try:
                # Skip hidden/venv folders
                if any(p.startswith('.') for p in path.parts) or "venv" in path.parts:
                    continue
                    
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    source = f.read()
                
                rel_path = str(path.relative_to(root)).replace("\\", "/")
                file_symbols = self._parse_source(source, rel_path)
                self.nodes.extend(file_symbols)
                
            except Exception as e:
                print(f"Failed to parse {path.name}: {e}")

        # 2. Linking Pass (Create Edges)
        self._build_edges()

        return {
            "root": str(root),
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": self.nodes,
            "edges": self.edges
        }

    # ==========================================================================
    # INTERNAL HELPERS
    # ==========================================================================

    def _parse_source(self, source: str, file_path: str) -> List[Dict]:
        """
        Uses Python's AST to extract surgical symbol info.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        visitor = SurgicalVisitor(file_path)
        visitor.visit(tree)
        return visitor.symbols

    def _build_edges(self):
        """
        Resolves 'calls' strings into explicit graph edges.
        """
        # Create a quick lookup map: "my_function" -> NodeID
        # Note: This is a naive lookup (name collision possible). 
        # A robust version would use "module.class.method" fully qualified names.
        name_map = {n['name']: n['id'] for n in self.nodes}

        for node in self.nodes:
            source_id = node['id']
            calls = node.get('calls', [])
            
            for target_name in calls:
                if target_name in name_map:
                    target_id = name_map[target_name]
                    
                    # Avoid self-loops for cleanliness
                    if source_id != target_id:
                        self.edges.append({
                            "source": source_id,
                            "target": target_id,
                            "type": "calls"
                        })

# ==============================================================================
# SELF-TEST / RUNNER
# ==============================================================================
if __name__ == "__main__":
    # Defaults to current directory
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    
    print(f"Mapping Logic in: {target_dir}")
    grapher = CodeGrapherMS()
    print(f"Service Ready: {grapher}")
    
    graph_data = grapher.scan_directory(target_dir)
    
    print(f"\n--- Scan Complete ---")
    print(f"Nodes Found: {graph_data.get('node_count', 0)}")
    print(f"Edges Built: {graph_data.get('edge_count', 0)}")
    
    # Save to JSON for inspection
    out_file = "code_graph_dump.json"
    with open(out_file, "w") as f:
        json.dump(graph_data, f, indent=2)
    print(f"Graph saved to {out_file}")