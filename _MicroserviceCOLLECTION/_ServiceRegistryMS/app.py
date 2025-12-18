import ast
import json
import uuid
import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION
# ==============================================================================
OUTPUT_FILE = "registry.json"
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("ServiceRegistry")
# ==============================================================================

@service_metadata(
name="ServiceRegistry",
version="1.0.0",
description="Scans a library of Python microservices and generates standardized JSON Service Tokens.",
tags=["introspection", "registry", "parsing"],
capabilities=["filesystem:read", "filesystem:write"]
)
class ServiceRegistryMS:
    """
The Tokenizer (v2): Scans a library of Python microservices and generates
standardized JSON 'Service Tokens'.
Feature: Hybrid AST/Regex parsing for maximum robustness.
"""
def __init__(self, config: Optional[Dict[str, Any]] = None):
    self.config = config or {}
    self.root = Path(self.config.get("root_path", ".")).resolve()
    self.registry = []

    @service_endpoint(
    inputs={"save_to": "str"},
    outputs={"registry": "List[Dict]"},
    description="Scans the file system for microservices and builds a registry.",
    tags=["introspection", "scan"],
    side_effects=["filesystem:read", "filesystem:write"]
    )
    def scan(self, save_to: str = OUTPUT_FILE) -> List[Dict]:
    log.info(f"Scanning for microservices in: {self.root}")
        
        # 1. Walk directories
        for item in self.root.iterdir():
            if item.is_dir() and item.name.startswith("_") and item.name.endswith("MS"):
                self._process_folder(item)
        
        # 2. Save Registry
        try:
            with open(save_to, "w", encoding="utf-8") as f:
                json.dump(self.registry, f, indent=2)
            log.info(f"✅ Registry built. Found {len(self.registry)} services. Saved to {save_to}")
        except Exception as e:
            log.error(f"Failed to save registry: {e}")
            
        return self.registry

    def _process_folder(self, folder: Path):
        # Find the main .py file (usually matches folder name, or is the only .py file)
        candidates = list(folder.glob("*.py"))
        for file in candidates:
            if file.name.startswith("__"): continue
            
            token = self._tokenize_file(file)
            if token:
                self.registry.append(token)
                log.info(f"  + Tokenized: {token['name']}")
                break 

    def _tokenize_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            
            # Attempt 1: Strict AST Parsing (The "Right" Way)
            try:
                return self._ast_parse(source, file_path)
            except Exception:
                # Attempt 2: Regex Fallback (The "Survival" Way)
                return self._regex_parse(source, file_path)
                
        except Exception as e:
            log.warning(f"  - Failed to read {file_path.name}: {e}")
            return None

    def _ast_parse(self, source: str, file_path: Path):
tree = ast.parse(source)
        target_class = None
        
        # Find class ending in 'MS'
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("MS"):
                target_class = node
                break
        
        if not target_class: return None

        # Extract Metadata
        return self._build_token(
            name=target_class.name,
            doc=ast.get_docstring(target_class) or "",
            methods=[
                (n.name, [a.arg for a in n.args.args if a.arg != 'self'], ast.get_docstring(n) or "")
                for n in target_class.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
            ],
            deps=self._extract_ast_imports(tree),
            file_path=file_path
        )

    def _regex_parse(self, source: str, file_path: Path):
        # Find class definition
        class_match = re.search(r'class\s+(\w+MS)', source)
        if not class_match: return None
        name = class_match.group(1)
        
        # Find methods (def name(args):)
        methods = []
        for match in re.finditer(r'def\s+(\w+)\s*\((.*?)\):', source):
            m_name = match.group(1)
            if not m_name.startswith("_"):
                args = [a.strip().split(':')[0] for a in match.group(2).split(',') if a.strip() != 'self']
                methods.append((m_name, args, "Regex extracted"))
                
        return self._build_token(name, "Parsed via Regex", methods, [], file_path)

    def _build_token(self, name, doc, methods, deps, file_path):
        # Generate deterministic ID
        namespace = uuid.uuid5(uuid.NAMESPACE_DNS, "microservice.library")
        token_id = f"MS_{uuid.uuid5(namespace, name).hex[:8].upper()}"
        
        method_dict = {
            m_name: {"args": m_args, "doc": m_doc.strip()} 
            for m_name, m_args, m_doc in methods
        }

        return {
            "token_id": token_id,
            "name": name,
            "path": str(file_path.relative_to(self.root)).replace('\\', '/'),
            "description": doc.strip(),
            "methods": method_dict,
            "dependencies": sorted(deps)
        }

    def _extract_ast_imports(self, tree):
        deps = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names: deps.add(n.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module: deps.add(node.module.split('.')[0])
        return list(deps)

if __name__ == "__main__":
svc = ServiceRegistryMS()
print("Service ready:", svc)
svc.scan()
