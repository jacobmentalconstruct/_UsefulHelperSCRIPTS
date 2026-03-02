from orchestration import *


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

if __name__ == '__main__':
    sys.exit(main())