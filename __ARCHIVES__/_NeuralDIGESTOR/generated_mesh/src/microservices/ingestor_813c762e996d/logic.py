import sys
sys.path.append('..')
from orchestration import *
import json
from typing import Dict, List, Tuple, Optional, Iterable, Any, Set
from rdflib import Graph as RDFGraph, Namespace, URIRef, Literal

class Ingestor:
    SUPPORTED_EXTENSIONS = {
        '.py': PythonParser(),
        '.md': TextParser(),
        '.markdown': TextParser(),
        '.txt': TextParser(),
    }

    def __init__(self, project_path: str, data_store: str, project_name: str) -> None:
        self.project_path = os.path.abspath(project_path)
        self.data_store = os.path.abspath(data_store)
        self.project_name = project_name
        self.cas = ContentAddressableStore(os.path.join(self.data_store, 'verbatim'))
        self.property_graph = PropertyGraph()
        self.knowledge_graph = KnowledgeGraph(project_name)
        self.vector_store = VectorStore()
        self.all_blocks: List[Block] = []
        self.edge_refs: List[EdgeRef] = []
        self.missing_links: List[Dict[str, Any]] = []
        os.makedirs(self.data_store, exist_ok=True)
        os.makedirs(os.path.join(self.data_store, 'manifests'), exist_ok=True)

    def discover_files(self) -> List[str]:
        files: List[str] = []
        for root, dirs, filenames in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'node_modules')]
            for fname in filenames:
                if fname.startswith('.'):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.SUPPORTED_EXTENSIONS:
                    files.append(os.path.join(root, fname))
        return files

    def ingest(self) -> None:
        files = self.discover_files()
        # parse files
        for fpath in files:
            rel_path = os.path.relpath(fpath, self.project_path)
            parser = self.SUPPORTED_EXTENSIONS.get(os.path.splitext(fpath)[1].lower(), TextParser())
            blocks, edges = parser.parse(fpath, rel_path)
            self.all_blocks.extend(blocks)
            self.edge_refs.extend(edges)
        # write blobs and add to graphs
        name_to_blocks: Dict[Tuple[str, str], List[Block]] = {}
        for block in self.all_blocks:
            block.hash = self.cas.write_blob(block.text)
            # create IRI for block
            block.iri = self.knowledge_graph.iri(block.file_path, block.name)
            # property graph node
            self.property_graph.add_node(block.hash,
                                         type=block.type,
                                         name=block.name,
                                         file=block.file_path,
                                         start_line=block.start_line,
                                         end_line=block.end_line)
            # knowledge graph node
            self.knowledge_graph.add_node(block.iri, block.type, block.name, block.file_path)
            # index by name for later resolution
            name_to_blocks.setdefault((block.file_path, block.name), []).append(block)
        # also index by simple name across files
        name_to_global: Dict[str, List[Block]] = {}
        for block in self.all_blocks:
            name_to_global.setdefault(block.name, []).append(block)
        # process edge refs
        edge_set: Set[Tuple[str, str, str]] = set()
        for e in self.edge_refs:
            # find source blocks (prefer same file)
            src_blocks = name_to_blocks.get((e.file_path, e.source_name)) or name_to_global.get(e.source_name, [])
            tgt_blocks = name_to_blocks.get((e.file_path, e.target_name)) or name_to_global.get(e.target_name, [])
            if not tgt_blocks:
                self.missing_links.append({
                    'source': e.source_name,
                    'missing_symbol': e.target_name,
                    'edge_type': e.edge_type,
                    'file': e.file_path,
                    'line': e.lineno,
                })
                continue
            for sb in src_blocks:
                for tb in tgt_blocks:
                    key = (sb.hash, tb.hash, e.edge_type)
                    if key in edge_set:
                        continue
                    edge_set.add(key)
                    # property graph edge
                    self.property_graph.add_edge(sb.hash, tb.hash, e.edge_type)
                    # knowledge graph triple
                    self.knowledge_graph.add_edge(sb.iri, e.edge_type, tb.iri)
        # fit vector store
        texts = [block.text for block in self.all_blocks]
        ids = [block.hash for block in self.all_blocks]
        self.vector_store.fit(texts, ids)
        # save graphs
        prop_path = os.path.join(self.data_store, 'property_graph.json')
        self.property_graph.save_json(prop_path)
        kg_path = os.path.join(self.data_store, 'knowledge_graph.ttl')
        self.knowledge_graph.save_ttl(kg_path)
        vec_base = os.path.join(self.data_store, 'vector_index')
        self.vector_store.save(vec_base)
        # write manifest
        self.write_manifest(prop_path, kg_path, vec_base)

    def write_manifest(self, prop_path: str, kg_path: str, vec_base: str) -> None:
        manifest = {
            'project': self.project_name,
            'version': '0.1',
            'blocks': [block.hash for block in self.all_blocks],
            'property_graph': os.path.relpath(prop_path, self.data_store),
            'knowledge_graph': os.path.relpath(kg_path, self.data_store),
            'vector_index': os.path.relpath(vec_base, self.data_store),
            'missing_links': self.missing_links,
        }
        with open(os.path.join(self.data_store, 'manifests', 'project_manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)

    def query(self, prompt: str, k: int = 5) -> Dict[str, Any]:
        """Map a natural language prompt to property and knowledge graph results.

        Returns a dictionary containing:
          - top_k: list of (block_hash, similarity) pairs
          - property_nodes: list of node dicts for the matching blocks
          - knowledge_triples: list of triples (subject, predicate, object) for matching blocks
        """
        results = self.vector_store.query(prompt, k)
        hashes = [h for h, _ in results]
        # property nodes
        nodes = []
        for nid, attrs in self.property_graph.graph.nodes(data=True):
            if nid in hashes:
                nodes.append({'id': nid, **attrs})
        # knowledge triples
        triples = []
        for h in hashes:
            # find block by hash
            block = next((b for b in self.all_blocks if b.hash == h), None)
            if block is None:
                continue
            subject = block.iri
            # retrieve triples where subject is the subject
            for pred, obj in self.knowledge_graph.graph.predicate_objects(subject=subject):
                triples.append((str(subject), str(pred), str(obj)))
        return {'top_k': results, 'property_nodes': nodes, 'knowledge_triples': triples}