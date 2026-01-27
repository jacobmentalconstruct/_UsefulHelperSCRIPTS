"""
SERVICE_NAME: _LibrarianMS
ENTRY_POINT: _LibrarianMS.py
INTERNAL_DEPENDENCIES: microservice_std_lib
EXTERNAL_DEPENDENCIES: requests
"""
import importlib.util
if importlib.util.find_spec('requests') is None:
    print('! MISSING DEPENDENCY: pip install requests')
import ast
import os
import datetime
import logging
import json
import requests
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Any, Optional
from microservice_std_lib import service_metadata, service_endpoint
ENABLE_AI = True
OLLAMA_URL = 'http://localhost:11434/api/generate'
MODEL_WORKER = 'qwen2.5-coder:1.5b-cpu'
MODEL_ARCHITECT = 'qwen2.5-coder:3b-cpu'
MAX_WORKERS = 4
MAX_CONTEXT_CHARS = 16000
logger = logging.getLogger('Librarian')

@service_metadata(name='Librarian', version='3.0.0', description="Uses a swarm of local AI models to generate a 'Card Catalogue' of the microservice library.", tags=['documentation', 'ai', 'catalog', 'swarm'], capabilities=['filesystem:read', 'filesystem:write', 'network:outbound', 'compute:parallel'], internal_dependencies=['microservice_std_lib'], external_dependencies=['requests'])
class LibrarianMS:
    """
    The Swarm Librarian.
    Spawns concurrent AI workers to scan the codebase and create a system manifest.
    Optimized for Ryzen CPUs and 32GB RAM.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.root = Path(self.config.get('root_path', '.')).resolve()

    @service_endpoint(inputs={'output_file': 'str'}, outputs={'path': 'str', 'service_count': 'int'}, description='Unleashes the AI swarm to generate a catalog.', tags=['catalog', 'generate'], side_effects=['filesystem:write'])
    def generate_catalog(self, output_file: str='LIBRARY_CATALOGUE.md') -> Dict[str, Any]:
        """
        Main entry point. Uses ThreadPoolExecutor for parallel processing.
        """
        services = []
        logger.info(f'🚀 Launching Swarm (Workers: {MAX_WORKERS}, Model: {MODEL_WORKER})...')
        ms_files = list(self.root.glob('*MS.py'))
        targets = [f for f in ms_files if f.name.startswith('_')]
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {executor.submit(self._inspect_file, f): f for f in targets}
            for future in concurrent.futures.as_completed(future_to_file):
                f_path = future_to_file[future]
                try:
                    info = future.result()
                    if info:
                        services.append(info)
                        print(f'  [Worker Completed] {f_path.name}')
                except Exception as e:
                    logger.error(f'  [Worker Failed] {f_path.name}: {e}')
        services.sort(key=lambda x: x['name'])
        system_summary = self._generate_system_summary(services)
        content = self._format_markdown(services, system_summary)
        out_path = self.root / output_file
        out_path.write_text(content, encoding='utf-8')
        logger.info(f'✅ Catalog generated: {out_path} ({len(services)} services)')
        return {'path': str(out_path), 'service_count': len(services)}

    def _inspect_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Worker Task: AST Parse -> AI Enrichment.
        """
        try:
            source = file_path.read_text(encoding='utf-8')
            tree = ast.parse(source)
            meta = {'filename': file_path.name, 'name': file_path.stem, 'description': '', 'tags': [], 'endpoints': [], 'ai_enriched': False}
            target_node = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and 'MS' in node.name:
                    target_node = node
                    break
            if not target_node:
                return None
            meta['name'] = target_node.name
            meta['description'] = ast.get_docstring(target_node) or ''
            if ENABLE_AI and len(meta['description']) < 10:
                prompt = f'Read this Python class and write a 1-sentence description of its purpose. Be technical and concise.\n\nCode snippet:\n{source[:2000]}'
                ai_desc = self._query_ollama(MODEL_WORKER, prompt)
                if ai_desc:
                    meta['description'] = f'✨ {ai_desc}'
                    meta['ai_enriched'] = True
            for item in target_node.body:
                if isinstance(item, ast.FunctionDef) and (not item.name.startswith('_')):
                    args = [a.arg for a in item.args.args if a.arg != 'self']
                    doc = ast.get_docstring(item) or ''
                    meta['endpoints'].append({'name': item.name, 'args': args, 'doc': doc.split('\n')[0]})
            return meta
        except Exception as e:
            logger.warning(f'Failed to inspect {file_path.name}: {e}')
            return None

    def _generate_system_summary(self, services: List[Dict]) -> str:
        """
        Architect Task: Analyzes the entire system map using the larger model.
        """
        if not ENABLE_AI:
            return 'Auto-generated catalog of available microservices.'
        logger.info(f'🧠 Architect ({MODEL_ARCHITECT}) is analyzing system structure...')
        service_list = '\n'.join([f"- {s['name']}: {s['description']}" for s in services])
        if len(service_list) > MAX_CONTEXT_CHARS:
            service_list = service_list[:MAX_CONTEXT_CHARS] + '\n...(truncated)...'
        prompt = f"You are a System Architect. Analyze this list of microservices. Write a brief 'Executive Summary' (max 150 words) that explains what this system is capable of. Group capabilities logically (e.g., 'UI Layer', 'Data Ingestion', 'Core Logic').\n\nService List:\n{service_list}"
        summary = self._query_ollama(MODEL_ARCHITECT, prompt)
        return summary or 'System analysis failed.'

    def _query_ollama(self, model: str, prompt: str) -> str:
        """Helper to hit local Ollama instance."""
        try:
            payload = {'model': model, 'prompt': prompt, 'stream': False, 'options': {'temperature': 0.2, 'num_ctx': 4096}}
            timeout = 60 if model == MODEL_ARCHITECT else 20
            res = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
            if res.status_code == 200:
                return res.json().get('response', '').strip()
        except Exception:
            pass
        return ''

    def _format_markdown(self, services: List[Dict], summary: str) -> str:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        md = [f'# 📚 Microservice Library Card Catalogue', f'> **Generated**: {timestamp}', f'> **Total Services**: {len(services)}', f'> **Swarm Configuration**: `{MAX_WORKERS}` Workers (`{MODEL_WORKER}`), 1 Architect (`{MODEL_ARCHITECT}`)', '', '## 🧠 System Architecture Overview', summary, '', '## 📇 Index']
        for s in services:
            desc_short = s['description'].split('\n')[0][:80]
            md.append(f"- **[{s['name']}](#{s['name'].lower()})**: {desc_short}")
        md.append('\n---\n')
        for s in services:
            md.append(f"### {s['name']}")
            md.append(f"**File**: `{s['filename']}`")
            md.append(f"**Description**: {s['description']}")
            if s['endpoints']:
                md.append('\n| Endpoint | Inputs | Summary |')
                md.append('| :--- | :--- | :--- |')
                for ep in s['endpoints']:
                    args_str = ', '.join(ep['args']) or 'None'
                    md.append(f"| `{ep['name']}` | `{args_str}` | {ep['doc']} |")
            md.append('\n---\n')
        return '\n'.join(md)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    lib = LibrarianMS()
    print('Service Ready:', lib)
    res = lib.generate_catalog()
    print(f"Catalog created at: {res['path']}")
