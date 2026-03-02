import sys
sys.path.append('..')
from orchestration import *
import ast

class PythonParser(Parser):
    def parse(self, file_path: str, rel_path: str) -> Tuple[List[Block], List[EdgeRef]]:
        blocks: List[Block] = []
        edges: List[EdgeRef] = []
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        lines = source.splitlines()
        try:
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError:
            # treat whole file as one block
            blocks.append(Block(text=source, type='module', name=os.path.basename(rel_path),
                                file_path=rel_path, start_line=1, end_line=len(lines)))
            return blocks, edges
        module_block = Block(text=source, type='module', name=rel_path, file_path=rel_path,
                             start_line=1, end_line=len(lines))
        blocks.append(module_block)
        # extract functions and classes
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = getattr(node, 'lineno', 1)
                end = getattr(node, 'end_lineno', start)
                text = '\n'.join(lines[start-1:end])
                blocks.append(Block(text=text, type='function', name=node.name,
                                    file_path=rel_path, start_line=start, end_line=end))
                edges.append(EdgeRef(source_name=rel_path, target_name=node.name,
                                     edge_type='defines', file_path=rel_path, lineno=start))
            elif isinstance(node, ast.ClassDef):
                start = getattr(node, 'lineno', 1)
                end = getattr(node, 'end_lineno', start)
                text = '\n'.join(lines[start-1:end])
                blocks.append(Block(text=text, type='class', name=node.name,
                                    file_path=rel_path, start_line=start, end_line=end))
                edges.append(EdgeRef(source_name=rel_path, target_name=node.name,
                                     edge_type='defines', file_path=rel_path, lineno=start))
        # extract calls and inheritance
        class FuncVisitor(ast.NodeVisitor):
            def __init__(self, current_name: str) -> None:
                self.current_name = current_name
                self.local_edges: List[EdgeRef] = []
            def visit_Call(self, call_node: ast.Call) -> None:
                func = call_node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name:
                    self.local_edges.append(EdgeRef(source_name=self.current_name, target_name=name,
                                                    edge_type='dependsOn', file_path=rel_path,
                                                    lineno=getattr(call_node, 'lineno', 0)))
                self.generic_visit(call_node)
            def visit_ClassDef(self, cls_node: ast.ClassDef) -> None:
                for base in cls_node.bases:
                    base_name = None
                    if isinstance(base, ast.Name):
                        base_name = base.id
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                    if base_name:
                        self.local_edges.append(EdgeRef(source_name=cls_node.name, target_name=base_name,
                                                        edge_type='childOf', file_path=rel_path,
                                                        lineno=getattr(cls_node, 'lineno', 0)))
                self.generic_visit(cls_node)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visitor = FuncVisitor(node.name)
                visitor.visit(node)
                edges.extend(visitor.local_edges)
            elif isinstance(node, ast.ClassDef):
                visitor = FuncVisitor(node.name)
                visitor.visit(node)
                edges.extend(visitor.local_edges)
        # imports
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append(EdgeRef(source_name=rel_path, target_name=alias.name,
                                         edge_type='dependsOn', file_path=rel_path,
                                         lineno=getattr(node, 'lineno', 0)))
            elif isinstance(node, ast.ImportFrom):
                modname = node.module or ''
                for alias in node.names:
                    fullname = f"{modname}.{alias.name}" if modname else alias.name
                    edges.append(EdgeRef(source_name=rel_path, target_name=fullname,
                                         edge_type='dependsOn', file_path=rel_path,
                                         lineno=getattr(node, 'lineno', 0)))
        return blocks, edges