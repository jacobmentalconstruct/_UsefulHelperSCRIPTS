#!/usr/bin/env python3
"""
Graph DB prototype for the Tri‑State Topological Cartridge.

This script ingests a project into three synchronized layers:
  * Verbatim layer: content‑addressable store of atomic text blocks (code, paragraphs).
  * Property graph: a directed property graph representing functional relationships.
  * Knowledge graph (RDF): triples capturing semantic identity and relations.
  * Vector field: a doc2vec embedding space enabling fuzzy, natural‑language queries.

The property graph is implemented using NetworkX (MultiDiGraph).  The knowledge
graph uses rdflib and defines a simple namespace for predicates.  The vector
field uses gensim's Doc2Vec along with sklearn's NearestNeighbors.

When ingesting a codebase, the pipeline parses supported files (Python, text),
atomizes them, stores raw blobs in the CAS, constructs both graphs, fits the
vector index, and writes manifests describing the resulting dataset.  A query
method is provided to map natural language prompts into the latent space and
retrieve related nodes from both graphs.

This prototype demonstrates how property graphs, knowledge graphs and
embeddings can be overlaid to create a relational topology for large‑scale AI
development, as described in the Tri‑State Topological Cartridge white paper.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Iterable, Any, Set

import networkx as nx
import numpy as np
from sklearn.neighbors import NearestNeighbors
import joblib
from gensim.models import Doc2Vec
from gensim.models.doc2vec import TaggedDocument
from rdflib import Graph as RDFGraph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS


###############################################################################
# Utility classes
###############################################################################


def normalize_text(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return '\n'.join([line.rstrip() for line in text.split('\n')])


class ContentAddressableStore:
    def __init__(self, root: str) -> None:
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    def _blob_path(self, digest: str) -> str:
        return os.path.join(self.root, digest[:2], f"{digest[2:]}.txt")

    def write_blob(self, data: str) -> str:
        norm = normalize_text(data)
        digest = hashlib.sha256(norm.encode('utf-8')).hexdigest()
        path = self._blob_path(digest)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                f.write(norm)
        return digest


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


class KnowledgeGraph:
    """RDF knowledge graph using rdflib."""

    def __init__(self, project_name: str) -> None:
        self.graph = RDFGraph()
        # Define a namespace for the project
        self.NS = Namespace(f"http://example.org/{project_name}/")
        # Define our own predicates
        self.P = Namespace(f"http://example.org/{project_name}/predicates#")
        # Bind prefixes for readability
        self.graph.bind('proj', self.NS)
        self.graph.bind('p', self.P)

    def iri(self, file_path: str, name: str) -> URIRef:
        # Create a URI for a code block or concept: project_name/file_path#name
        path_part = file_path.replace(os.sep, '/')
        return URIRef(self.NS + f"{path_part}#{name}")

    def add_node(self, iri: URIRef, node_type: str, name: str, file_path: str) -> None:
        # Add type triple and name/file metadata as literals
        self.graph.add((iri, RDF.type, Literal(node_type)))
        self.graph.add((iri, self.P.hasName, Literal(name)))
        self.graph.add((iri, self.P.inFile, Literal(file_path)))

    def add_edge(self, subject: URIRef, predicate: str, obj: URIRef) -> None:
        # Create predicate IRI
        pred = self.P[predicate]
        self.graph.add((subject, pred, obj))

    def save_ttl(self, path: str) -> None:
        self.graph.serialize(destination=path, format='turtle')


class VectorStore:
    """Doc2Vec-based vector store with nearest-neighbour search."""

    def __init__(self) -> None:
        self.model: Optional[Doc2Vec] = None
        self.ids: List[str] = []
        self.matrix: Optional[np.ndarray] = None
        self.nn: Optional[NearestNeighbors] = None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def fit(self, texts: List[str], ids: List[str], vector_size: int = 128, epochs: int = 40) -> None:
        docs = [TaggedDocument(words=self._tokenize(t), tags=[ids[i]]) for i, t in enumerate(texts)]
        model = Doc2Vec(vector_size=vector_size, min_count=1, workers=max(1, os.cpu_count() or 1))
        model.build_vocab(docs)
        model.train(docs, total_examples=len(docs), epochs=epochs)
        self.model = model
        self.ids = list(ids)
        vectors = [model.dv[doc_id] for doc_id in self.ids]
        self.matrix = np.vstack(vectors)
        self.nn = NearestNeighbors(n_neighbors=min(5, len(self.ids)), metric='cosine')
        self.nn.fit(self.matrix)

    def infer(self, text: str) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("VectorStore not fitted")
        return self.model.infer_vector(self._tokenize(text))

    def query(self, query_text: str, k: int = 5) -> List[Tuple[str, float]]:
        if self.matrix is None or self.nn is None or self.model is None:
            raise RuntimeError("VectorStore not fitted")
        qvec = self.infer(query_text).reshape(1, -1)
        distances, indices = self.nn.kneighbors(qvec, n_neighbors=min(k, len(self.ids)))
        results: List[Tuple[str, float]] = []
        for dist, idx in zip(distances[0], indices[0]):
            results.append((self.ids[idx], float(1 - dist)))
        return results

    def save(self, path: str) -> None:
        if self.model is None:
            raise RuntimeError("VectorStore not fitted")
        base, _ = os.path.splitext(path)
        self.model.save(base + '.model')
        with open(base + '.ids', 'w', encoding='utf-8') as f:
            json.dump(self.ids, f)

    def load(self, path: str) -> None:
        base, _ = os.path.splitext(path)
        self.model = Doc2Vec.load(base + '.model')
        with open(base + '.ids', 'r', encoding='utf-8') as f:
            self.ids = json.load(f)
        vectors = [self.model.dv[doc_id] for doc_id in self.ids]
        self.matrix = np.vstack(vectors)
        self.nn = NearestNeighbors(n_neighbors=min(5, len(self.ids)), metric='cosine')
        self.nn.fit(self.matrix)


###############################################################################
# Parser classes
###############################################################################


@dataclass
class Block:
    text: str
    type: str
    name: str
    file_path: str
    start_line: int
    end_line: int
    hash: Optional[str] = None
    iri: Optional[URIRef] = None


@dataclass
class EdgeRef:
    source_name: str
    target_name: str
    edge_type: str
    file_path: str
    lineno: int


class Parser:
    def parse(self, file_path: str, rel_path: str) -> Tuple[List[Block], List[EdgeRef]]:
        raise NotImplementedError


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


class TextParser(Parser):
    def parse(self, file_path: str, rel_path: str) -> Tuple[List[Block], List[EdgeRef]]:
        blocks: List[Block] = []
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        paragraphs = [p.strip('\n') for p in re.split(r'\n\s*\n', content) if p.strip()]
        line_idx = 1
        for i, para in enumerate(paragraphs):
            lines = para.split('\n')
            start = line_idx
            end = start + len(lines) - 1
            blocks.append(Block(text=para, type='paragraph', name=f"para{i+1}",
                                file_path=rel_path, start_line=start, end_line=end))
            line_idx = end + 2
        return blocks, []


###############################################################################
# Ingestor
###############################################################################


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


###############################################################################
# CLI
###############################################################################


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Ingest a project using property and knowledge graphs with a vector store.')
    parser.add_argument('--project-path', required=True, help='Path to the project directory to ingest')
    parser.add_argument('--data-store', required=True, help='Directory where the data store should be written')
    parser.add_argument('--project-name', required=True, help='Name of the project (used in IRIs)')
    parser.add_argument('--query', help='Optional prompt to query after ingestion')
    parser.add_argument('--top-k', type=int, default=5, help='Number of results to return for queries')
    args = parser.parse_args(argv)
    ingestor = Ingestor(args.project_path, args.data_store, args.project_name)
    ingestor.ingest()
    print(f"Ingestion complete. Data store created at {args.data_store}")
    if args.query:
        results = ingestor.query(args.query, args.top_k)
        print('Top matches:')
        for h, score in results['top_k']:
            print(f"  {h}: {score:.3f}")
        print('\nProperty nodes:')
        for node in results['property_nodes']:
            print(f"  {node}")
        print('\nKnowledge triples:')
        for triple in results['knowledge_triples']:
            print(f"  {triple}")
    return 0


if __name__ == '__main__':
    sys.exit(main())