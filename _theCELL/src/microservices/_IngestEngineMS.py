"""
SERVICE_NAME: _IngestEngineMS
ENTRY_POINT: _IngestEngineMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib
EXTERNAL_DEPENDENCIES: requests
"""
import importlib.util
import sys
REQUIRED = ['requests']
MISSING = []
for lib in REQUIRED:
    if importlib.util.find_spec(lib) is None:
        MISSING.append(lib)
if MISSING:
    print(f"MISSING DEPENDENCIES: {' '.join(MISSING)}")
    print('Please run: pip install requests')
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, Generator, List, Optional
import requests
from .microservice_std_lib import service_metadata, service_endpoint
from .base_service import BaseService
OLLAMA_API_URL = 'http://localhost:11434/api'

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
    Used to generate the 'DEPENDS_ON' edges in the Knowledge Graph.
    """

    def __init__(self):
        self.py_pattern = re.compile('^\\s*(?:from|import)\\s+([\\w\\.]+)')
        self.js_pattern = re.compile('(?:import\\s+.*?from\\s+[\\\'"]|require\\([\\\'"])([\\.\\/\\w\\-_]+)[\\\'"]')

    def extract_dependencies(self, content: str, file_path: str) -> List[str]:
        dependencies = []
        ext = os.path.splitext(file_path)[1].lower()
        lines = content.split('\n')
        for line in lines:
            match = None
            if ext == '.py':
                match = self.py_pattern.match(line)
            elif ext in ['.js', '.ts', '.tsx', '.jsx']:
                match = self.js_pattern.search(line)
            if match:
                raw_dep = match.group(1)
                clean_dep = raw_dep.split('.')[-1].split('/')[-1]
                if clean_dep not in dependencies:
                    dependencies.append(clean_dep)
        return dependencies

@service_metadata(name='IngestEngine', version='1.0.0', description='Reads files, chunks text, fetches embeddings, and weaves graph edges.', tags=['ingest', 'rag', 'parsing', 'embedding'], capabilities=['filesystem:read', 'network:outbound', 'db:sqlite'], side_effects=['db:write', 'network:outbound'], internal_dependencies=['base_service', 'microservice_std_lib'], external_dependencies=['requests'])
class IngestEngineMS(BaseService):
    """
    The Heavy Lifter: Reads files, chunks text, fetches embeddings,
    populates the Graph Nodes, and weaves Graph Edges.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        super().__init__('IngestEngine')
        self.config = config or {}
        self.db_path = self.config.get('db_path', 'knowledge.db')
        self.stop_signal = False
        self.weaver = SynapseWeaver()
        self._init_db()

    def _init_db(self):
        """Ensures the target database has the required schema."""
        conn = sqlite3.connect(self.db_path)
        conn.execute('CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, path TEXT, last_updated REAL)')
        conn.execute('CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, file_id INT, chunk_index INT, content TEXT, embedding BLOB)')
        conn.execute('CREATE TABLE IF NOT EXISTS graph_nodes (id TEXT PRIMARY KEY, type TEXT, label TEXT, data_json TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS graph_edges (source TEXT, target TEXT, weight REAL)')
        conn.close()

    def abort(self):
        self.stop_signal = True

    def check_ollama_connection(self) -> bool:
        try:
            requests.get(f'{OLLAMA_API_URL}/tags', timeout=2)
            return True
        except:
            return False

    def get_available_models(self) -> List[str]:
        try:
            res = requests.get(f'{OLLAMA_API_URL}/tags')
            if res.status_code == 200:
                data = res.json()
                return [m['name'] for m in data.get('models', [])]
        except:
            pass
        return []

    @service_endpoint(inputs={'file_paths': 'List[str]', 'model_name': 'str'}, outputs={'status': 'IngestStatus'}, description='Processes a list of files, ingesting them into the knowledge graph.', tags=['ingest', 'processing'], mode='generator', side_effects=['db:write', 'network:outbound'])
    def process_files(self, file_paths: List[str], model_name: str='none') -> Generator[IngestStatus, None, None]:
        total = len(file_paths)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('PRAGMA synchronous = OFF')
        cursor.execute('PRAGMA journal_mode = MEMORY')
        node_registry = {}
        file_contents = {}
        for idx, file_path in enumerate(file_paths):
            if self.stop_signal:
                yield IngestStatus(file_path, 0, idx, total, 'Ingestion Aborted.')
                break
            filename = os.path.basename(file_path)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                file_contents[filename] = content
            except Exception as e:
                yield IngestStatus(file_path, idx / total * 100, idx, total, f'Error: {e}')
                continue
            try:
                cursor.execute('INSERT OR REPLACE INTO files (path, last_updated) VALUES (?, ?)', (file_path, time.time()))
                file_id = cursor.lastrowid
            except sqlite3.Error:
                continue
            cursor.execute('\n                INSERT OR REPLACE INTO graph_nodes (id, type, label, data_json)\n                VALUES (?, ?, ?, ?)\n            ', (filename, 'file', filename, json.dumps({'path': file_path})))
            node_registry[filename] = filename
            chunks = self._chunk_text(content)
            for i, chunk_text in enumerate(chunks):
                if self.stop_signal:
                    break
                embedding = None
                if model_name != 'none':
                    embedding = self._get_embedding(model_name, chunk_text)
                emb_blob = json.dumps(embedding).encode('utf-8') if embedding else None
                cursor.execute('\n                    INSERT INTO chunks (file_id, chunk_index, content, embedding)\n                    VALUES (?, ?, ?, ?)\n                ', (file_id, i, chunk_text, emb_blob))
                thought_frame = {'id': f'{file_id}_{i}', 'file': filename, 'chunk_index': i, 'content': chunk_text, 'vector_preview': embedding[:20] if embedding else [], 'concept_color': '#007ACC'}
                yield IngestStatus(current_file=filename, progress_percent=(idx + i / len(chunks)) / total * 100, processed_files=idx, total_files=total, log_message=f'Processing {filename}...', thought_frame=thought_frame)
            conn.commit()
        yield IngestStatus('Graph', 100, total, total, 'Weaving Knowledge Graph...')
        edge_count = 0
        for filename, content in file_contents.items():
            if self.stop_signal:
                break
            deps = self.weaver.extract_dependencies(content, filename)
            for dep in deps:
                target_id = None
                for potential_match in node_registry.keys():
                    if potential_match.startswith(dep + '.') or potential_match == dep:
                        target_id = potential_match
                        break
                if target_id and target_id != filename:
                    try:
                        cursor.execute('\n                            INSERT OR IGNORE INTO graph_edges (source, target, weight)\n                            VALUES (?, ?, 1.0)\n                        ', (filename, target_id))
                        edge_count += 1
                    except:
                        pass
        conn.commit()
        conn.close()
        yield IngestStatus(current_file='Complete', progress_percent=100, processed_files=total, total_files=total, log_message=f'Ingestion Complete. Created {edge_count} dependency edges.')

    def _chunk_text(self, text: str, chunk_size: int=1000, overlap: int=100) -> List[str]:
        if len(text) < chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks

    def _get_embedding(self, model: str, text: str) -> Optional[List[float]]:
        try:
            res = requests.post(f'{OLLAMA_API_URL}/embeddings', json={'model': model, 'prompt': text}, timeout=30)
            if res.status_code == 200:
                return res.json().get('embedding')
        except:
            return None
if __name__ == '__main__':
    TEST_DB = 'test_ingest_v2.db'
    engine = IngestEngineMS({'db_path': TEST_DB})
    print(f'Service Ready: {engine}')
    target_file = '__IngestEngineMS.py'
    if not os.path.exists(target_file):
        with open(target_file, 'w') as f:
            f.write("import os\nimport json\nprint('Hello World')")
    print(f'Running Ingest on {target_file}...')
    files = [target_file]
    for status in engine.process_files(files, 'none'):
        print(f'[{status.progress_percent:.0f}%] {status.log_message}')
    conn = sqlite3.connect(TEST_DB)
    edges = conn.execute('SELECT * FROM graph_edges').fetchall()
    nodes = conn.execute('SELECT * FROM graph_nodes').fetchall()
    print(f'\nResult: {len(nodes)} Nodes, {len(edges)} Edges.')
    conn.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if os.path.exists(target_file) and 'Hello World' in open(target_file).read():
        os.remove(target_file)
