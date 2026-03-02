import sys
sys.path.append('..')
from orchestration import *
import json
from rdflib import Graph as RDFGraph, Namespace, URIRef, Literal

class PropertyGraph:
    """Property graph built on NetworkX."""

    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()

    def add_node(self, node_id: str, **attrs: Any) -> None:
        if node_id in self.graph.nodes:
            for k, v in attrs.items():
                if k not in self.graph.nodes[node_id]:
                    self.graph.nodes[node_id][k] = v
        else:
            self.graph.add_node(node_id, **attrs)

    def add_edge(self, source: str, target: str, edge_type: str) -> None:
        self.graph.add_edge(source, target, type=edge_type)

    def to_dict(self) -> Dict[str, Any]:
        nodes = []
        for nid, attrs in self.graph.nodes(data=True):
            nd = {'id': nid}
            nd.update(attrs)
            nodes.append(nd)
        edges = []
        for src, tgt, attrs in self.graph.edges(data=True):
            edges.append({'source': src, 'target': tgt, 'type': attrs.get('type', '')})
        return {'nodes': nodes, 'edges': edges}

    def save_json(self, path: str) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)