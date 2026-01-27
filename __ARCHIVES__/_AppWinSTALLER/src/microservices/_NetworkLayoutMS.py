import importlib.util
import sys
import logging
from typing import List, Dict, Any, Tuple, Optional

# --- RUNTIME DEPENDENCY CHECK ---
REQUIRED = ["networkx"]
MISSING = []

for lib in REQUIRED:
    if importlib.util.find_spec(lib) is None:
        MISSING.append(lib)

if MISSING:
    print('\n' + '!'*60)
    print(f'MISSING DEPENDENCIES for _NetworkLayoutMS:')
    print(f'Run:  pip install {" ".join(MISSING)}')
    print('!'*60 + '\n')
    # Allow execution to proceed so the class definition loads, 
    # but actual usage will fail if import is missing.

# Import conditionally to avoid crashing immediately if missing
try:
    import networkx as nx
except ImportError:
    nx = None

from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION
# ==============================================================================
logger = logging.getLogger("NetLayout")

# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="NetworkLayout",
    version="1.0.0",
    description="Calculates visual (x,y) coordinates for graph nodes using NetworkX.",
    tags=["graph", "layout", "visualization"],
    capabilities=["compute"]
)
class NetworkLayoutMS:
    """
    The Topologist: Calculates visual coordinates for graph nodes using
    server-side algorithms (NetworkX). 
    Useful for generating static map snapshots or pre-calculating positions 
    to offload client-side rendering.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        if nx is None:
            logger.error("NetworkX is not installed. Layout calculations will fail.")

    @service_endpoint(
        inputs={"nodes": "List[str]", "edges": "List[Tuple]", "algorithm": "str"},
        outputs={"positions": "Dict[str, Tuple]"},
        description="Computes (x, y) coordinates for the given graph nodes and edges.",
        tags=["graph", "compute"],
        side_effects=[]
    )
    def calculate_layout(self, nodes: List[str], edges: List[Tuple[str, str]], 
                         algorithm: str = "spring", **kwargs) -> Dict[str, Tuple[float, float]]:
        """
        Computes (x, y) coordinates for the given graph.
        
        :param nodes: List of node IDs.
        :param edges: List of (source, target) tuples.
        :param algorithm: 'spring' (Force-directed) or 'circular'.
        :return: Dictionary {node_id: (x, y)}
        """
        if nx is None:
            return {}

        G = nx.DiGraph()
        G.add_nodes_from(nodes)
        G.add_edges_from(edges)
        
        logger.info(f"Computing layout for {len(nodes)} nodes, {len(edges)} edges using '{algorithm}'...")
        
        try:
            if algorithm == "circular":
                pos = nx.circular_layout(G)
            else:
                # Spring layout (Fruchterman-Reingold) is standard for knowledge graphs
                k_val = kwargs.get('k', 0.15) # Optimal distance between nodes
                iter_val = kwargs.get('iterations', 50)
                pos = nx.spring_layout(G, k=k_val, iterations=iter_val, seed=42)
                
            # Convert numpy arrays to simple lists/tuples for JSON serialization
            return {n: (float(p[0]), float(p[1])) for n, p in pos.items()}
            
        except Exception as e:
            logger.error(f"Layout calculation failed: {e}")
            return {}


# --- Independent Test Block ---
if __name__ == "__main__":
    # Setup basic logging for standalone test
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    layout = NetworkLayoutMS()
    print("Service ready:", layout)
    
    if nx:
        # 1. Define a simple graph
        test_nodes = ["Main", "Utils", "Config", "DB", "Auth"]
        test_edges = [
            ("Main", "Utils"),
            ("Main", "Config"),
            ("Main", "DB"),
            ("Main", "Auth"),
            ("DB", "Config"),
            ("Auth", "DB")
        ]
        
        # 2. Compute Layout
        positions = layout.calculate_layout(test_nodes, test_edges, k=0.5)
        
        print("--- Calculated Positions ---")
        for node, (x, y) in positions.items():
            print(f"{node:<10}: ({x: .4f}, {y: .4f})")
    else:
        print("Skipping test: NetworkX not found.")