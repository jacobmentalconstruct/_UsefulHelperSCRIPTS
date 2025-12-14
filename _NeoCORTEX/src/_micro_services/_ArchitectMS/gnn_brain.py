import sqlite3
import torch
import json
import struct
from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv
import torch.nn.functional as F

class CodeGraphBrain:
    def __init__(self, db_path):
        self.db_path = db_path
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
    def load_graph_from_neocortex(self):
        """
        Bridges _NeoCORTEX SQLite tables to a PyTorch Geometric Graph.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 1. Load Nodes & Features (The Embeddings you already have!)
        # We average chunk embeddings to get a single 'File Embedding'
        print("Loading embeddings...")
        sql = """
            SELECT f.path, c.embedding 
            FROM files f 
            JOIN chunks c ON f.id = c.file_id
        """
        cursor.execute(sql)
        
        node_map = {} # path -> index
        x_list = []   # features
        
        raw_data = cursor.fetchall()
        
        # Aggregate embeddings per file (Simple mean)
        temp_features = {}
        for path, emb_blob in raw_data:
            if not emb_blob: continue
            # Deserialize the BLOB from sqlite-vec format or JSON
            try:
                # Assuming JSON based on ingest_engine.py line 125
                vec = json.loads(emb_blob) 
                if path not in temp_features: temp_features[path] = []
                temp_features[path].append(vec)
            except: pass

        for i, (path, vecs) in enumerate(temp_features.items()):
            node_map[path] = i
            # Average the chunk vectors to get a File Vector
            avg_vec = torch.tensor(vecs).mean(dim=0)
            x_list.append(avg_vec)

        # 2. Load Edges (Your SynapseWeaver data)
        print("Loading edges...")
        cursor.execute("SELECT source, target FROM graph_edges")
        edge_list = []
        for src, tgt in cursor.fetchall():
            if src in node_map and tgt in node_map:
                edge_list.append([node_map[src], node_map[tgt]])
                # Add reverse edge for undirected graph
                edge_list.append([node_map[tgt], node_map[src]])

        conn.close()

        # 3. Construct PyG Data
        x = torch.stack(x_list) # Node Features [Num_Nodes, Hidden_Dim]
        edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
        
        data = Data(x=x, edge_index=edge_index)
        return data.to(self.device), node_map

    def train_architect(self, data):
        """Train a tiny GNN to understand code structure"""
        model = GraphSAGE(data.num_features, 64, data.num_features).to(self.device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        
        print("Training Architect Brain...")
        model.train()
        for epoch in range(100): # Fast training loop
            optimizer.zero_grad()
            z = model(data.x, data.edge_index)
            
            # Self-Supervised: Try to reconstruct the graph edges
            # (Predict existing links)
            out = (z[data.edge_index[0]] * z[data.edge_index[1]]).sum(dim=-1)
            loss = F.binary_cross_entropy_with_logits(out, torch.ones_like(out))
            
            loss.backward()
            optimizer.step()
            
            if epoch % 20 == 0:
                print(f"Epoch {epoch}: Loss {loss.item():.4f}")
        
        return model

# --- The Model ---
class GraphSAGE(torch.nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, out_channels)
    
    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = self.conv2(x, edge_index)
        return x # Returns new, "context-aware" embeddings

if __name__ == "__main__":
    # Test run
    brain = CodeGraphBrain("./cortex_dbs/_NeoCORTEX_FirstIngestion.db")
    graph, mappings = brain.load_graph_from_neocortex()
    model = brain.train_architect(graph)
    print("Brain Trained!")