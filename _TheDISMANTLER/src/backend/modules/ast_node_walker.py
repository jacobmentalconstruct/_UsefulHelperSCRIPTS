"""
AST Node Walker – Recursive AST walking and metadata generation.
Extends the base ast_lens with deeper analysis for:
- Import tracking per node
- Cross-reference mapping
- Entity extraction (classes, methods, variables, decorators)
- Hierarchical metadata for the Graph Lens UI

Pure logic module. Zero UI dependencies.
"""
import ast
import os
from typing import Dict, List, Optional, Set


class ASTNode:
    """Represents a node in the semantic tree with rich metadata."""

    __slots__ = (
        "name", "kind", "start_line", "end_line", "depth",
        "parent", "children", "imports", "references", "decorators",
    )

    def __init__(self, name, kind, start_line, end_line, depth=0):
        self.name = name
        self.kind = kind  # 'class', 'function', 'method', 'variable', 'import'
        self.start_line = start_line
        self.end_line = end_line
        self.depth = depth
        self.parent = None
        self.children: List["ASTNode"] = []
        self.imports: Set[str] = set()
        self.references: Set[str] = set()
        self.decorators: List[str] = []

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "depth": self.depth,
            "parent": self.parent,
            "children": [c.to_dict() for c in self.children],
            "imports": list(self.imports),
            "references": list(self.references),
            "decorators": self.decorators,
        }


class ASTNodeWalker:
    """
    Walks a Python AST and extracts a rich semantic tree.
    Produces nodes with import tracking, cross-references, and
    decorator metadata for populating the Graph Lens.
    """

    def __init__(self):
        self.nodes: List[ASTNode] = []
        self.entities: List[Dict] = []  # flat list for graph lens
        self.edges: List[Dict] = []     # relationships between entities

    def walk_file(self, file_path: str) -> List[ASTNode]:
        """
        Parse a file and return the full node tree.
        Also populates self.entities and self.edges.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        return self.walk_source(source, file_path)

    def walk_source(self, source: str, file_path: str = "<string>") -> List[ASTNode]:
        """Parse source code and build the node tree."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        self.nodes = []
        self.entities = []
        self.edges = []

        # Extract module-level imports
        module_imports = self._extract_imports(tree)

        # Walk top-level definitions
        self._walk_body(tree.body, depth=0, parent_name=None, module_imports=module_imports)

        return self.nodes

    def _walk_body(self, body, depth, parent_name, module_imports):
        """Recursively walk AST body nodes."""
        for node in body:
            if isinstance(node, ast.ClassDef):
                self._process_class(node, depth, parent_name, module_imports)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if parent_name else "function"
                self._process_function(node, kind, depth, parent_name, module_imports)
            elif isinstance(node, ast.Assign):
                self._process_assignment(node, depth, parent_name)

    def _process_class(self, node: ast.ClassDef, depth, parent_name, module_imports):
        """Extract a class definition and its members."""
        ast_node = ASTNode(
            name=node.name,
            kind="class",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            depth=depth,
        )
        ast_node.parent = parent_name
        ast_node.imports = module_imports.copy()
        ast_node.decorators = [self._decorator_name(d) for d in node.decorator_list]
        ast_node.references = self._extract_references(node)

        # Add entity for graph
        self.entities.append({
            "name": node.name,
            "kind": "class",
            "line": node.lineno,
            "parent": parent_name,
        })

        # Base class edges
        for base in node.bases:
            base_name = self._node_name(base)
            if base_name:
                self.edges.append({
                    "source": node.name,
                    "target": base_name,
                    "kind": "inherits",
                })

        # Walk class body
        self._walk_body(node.body, depth + 1, node.name, module_imports)

        # Collect children from self.nodes at depth+1
        children = [n for n in self.nodes if n.parent == node.name and n.depth == depth + 1]
        ast_node.children = children

        self.nodes.append(ast_node)

    def _process_function(self, node, kind, depth, parent_name, module_imports):
        """Extract a function or method definition."""
        ast_node = ASTNode(
            name=node.name,
            kind=kind,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            depth=depth,
        )
        ast_node.parent = parent_name
        ast_node.imports = module_imports.copy()
        ast_node.decorators = [self._decorator_name(d) for d in node.decorator_list]
        ast_node.references = self._extract_references(node)

        self.entities.append({
            "name": node.name,
            "kind": kind,
            "line": node.lineno,
            "parent": parent_name,
        })

        # Function call edges
        for ref in ast_node.references:
            self.edges.append({
                "source": node.name,
                "target": ref,
                "kind": "calls",
            })

        self.nodes.append(ast_node)

    def _process_assignment(self, node: ast.Assign, depth, parent_name):
        """Extract module/class-level variable assignments."""
        for target in node.targets:
            name = self._node_name(target)
            if name and name.isupper():  # Only constants (ALL_CAPS)
                ast_node = ASTNode(
                    name=name,
                    kind="variable",
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    depth=depth,
                )
                ast_node.parent = parent_name
                self.nodes.append(ast_node)

                self.entities.append({
                    "name": name,
                    "kind": "variable",
                    "line": node.lineno,
                    "parent": parent_name,
                })

    # ── extraction helpers ──────────────────────────────────

    @staticmethod
    def _extract_imports(tree: ast.AST) -> Set[str]:
        """Collect all import names from an AST."""
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        return imports

    @staticmethod
    def _extract_references(node: ast.AST) -> Set[str]:
        """Extract function/class names referenced within a node."""
        refs = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                name = ASTNodeWalker._node_name(child.func)
                if name:
                    refs.add(name)
            elif isinstance(child, ast.Attribute):
                if isinstance(child.value, ast.Name):
                    refs.add(f"{child.value.id}.{child.attr}")
        return refs

    @staticmethod
    def _node_name(node) -> Optional[str]:
        """Extract a readable name from an AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None

    @staticmethod
    def _decorator_name(node) -> str:
        """Extract the name of a decorator."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        elif isinstance(node, ast.Call):
            return ASTNodeWalker._decorator_name(node.func)
        return "unknown"

    # ── output helpers ──────────────────────────────────────

    def get_entity_list(self) -> List[Dict]:
        """Return flat entity list for the Graph Lens UI."""
        return self.entities

    def get_edge_list(self) -> List[Dict]:
        """Return relationship edges for the Graph Lens UI."""
        return self.edges

    def get_entity_types(self) -> List[str]:
        """Return unique entity types found."""
        return sorted(set(e["kind"] for e in self.entities))

    def format_tree(self) -> str:
        """Format the node tree as an indented string."""
        lines = []
        # Sort top-level nodes by line
        top = sorted(
            [n for n in self.nodes if n.parent is None],
            key=lambda n: n.start_line,
        )
        for node in top:
            self._format_node(node, lines, indent=0)
        return "\n".join(lines) if lines else "(no structure detected)"

    def _format_node(self, node: ASTNode, out: List[str], indent: int):
        prefix = "  " * indent
        icons = {"class": "\u25B8", "function": "\u25CB", "method": "\u25CB", "variable": "\u25AA"}
        icon = icons.get(node.kind, "\u25CF")
        decorators = f" @{', @'.join(node.decorators)}" if node.decorators else ""
        out.append(f"{prefix}{icon} {node.kind} {node.name}{decorators}  (L{node.start_line}-{node.end_line})")
        for child in sorted(node.children, key=lambda c: c.start_line):
            self._format_node(child, out, indent + 1)
