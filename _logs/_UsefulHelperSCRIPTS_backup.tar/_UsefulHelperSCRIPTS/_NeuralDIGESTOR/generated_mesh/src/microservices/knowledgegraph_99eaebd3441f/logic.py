import sys
sys.path.append('..')
from orchestration import *
from rdflib import Graph as RDFGraph, Namespace, URIRef, Literal

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