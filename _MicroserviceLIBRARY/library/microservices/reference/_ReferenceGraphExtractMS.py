import json
import re
import sqlite3
import time
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceGraphExtractMS',
    version='1.0.0',
    description='Pilfered from pipeline/extract.py. Parses extractor JSON output and writes structural graph edges.',
    tags=['pipeline', 'graph', 'extraction'],
    capabilities=['compute', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceGraphExtractMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'raw_text': 'str'}, outputs={'parsed': 'dict'}, description='Parse extractor model output JSON, stripping markdown code fences if needed.', tags=['graph', 'extract'])
    def parse_extractor_output(self, raw_text: str) -> Dict[str, Any]:
        raw = raw_text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return {'entities': [], 'relationships': []}
            data.setdefault('entities', [])
            data.setdefault('relationships', [])
            return data
        except Exception:
            return {'entities': [], 'relationships': []}

    @service_endpoint(inputs={'entities': 'list'}, outputs={'normalized': 'list'}, description='Normalize extracted entities into canonical records.', tags=['graph', 'entities'])
    def normalize_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for ent in entities:
            label = str(ent.get('text', '')).strip()
            if not label:
                continue
            out.append({
                'key': label.lower(),
                'label': label,
                'entity_type': ent.get('type', 'CONCEPT'),
                'salience': float(ent.get('salience', 0.5)),
            })
        return out

    @service_endpoint(inputs={'graph_node_ids': 'list'}, outputs={'edges': 'list'}, description='Build PRECEDES structural edges between sequential chunk graph nodes.', tags=['graph', 'edges'])
    def build_structural_edges(self, graph_node_ids: List[str]) -> List[Dict[str, Any]]:
        edges = []
        for i in range(len(graph_node_ids) - 1):
            edges.append({'src_node_id': graph_node_ids[i], 'dst_node_id': graph_node_ids[i + 1], 'edge_type': 'PRECEDES', 'weight': 1.0})
        return edges

    @service_endpoint(inputs={'db_path': 'str', 'graph_node_ids': 'list'}, outputs={'written': 'int'}, description='Write PRECEDES structural edges to graph_edges table.', tags=['graph', 'db'], side_effects=['db:write'])
    def write_structural_edges(self, db_path: str, graph_node_ids: List[str]) -> int:
        edges = self.build_structural_edges(graph_node_ids)
        conn = sqlite3.connect(db_path)
        try:
            for idx, edge in enumerate(edges):
                edge_id = f"precedes_{idx}_{edge['src_node_id']}_{edge['dst_node_id']}"
                conn.execute(
                    "INSERT INTO graph_edges (edge_id, src_node_id, dst_node_id, edge_type, weight) VALUES (?, ?, ?, 'PRECEDES', ?)",
                    (edge_id, edge['src_node_id'], edge['dst_node_id'], edge['weight']),
                )
            conn.commit()
            return len(edges)
        finally:
            conn.close()

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}
