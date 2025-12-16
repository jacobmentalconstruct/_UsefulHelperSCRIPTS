[ YOUR CARTRIDGE (.db) ]
│
├── 1. The Archive (Verbatim Storage) 
│   └── Table: 'files'
│       ├── vfs_path: "src/main.py"      (Hierarchy)
│       ├── content:  "import os..."     (Raw Text for LLM reading)
│       └── blob:     [Binary Data]      (Original PDF/Image backup)
│
├── 2. The Index (Semantic Search)
│   ├── Table: 'chunks'                  (Text Segments)
│   │   └── content: "def scan_path..."
│   └── Table: 'vec_items' (COMING NOW)  (Mathematical Index)
│       └── embedding: [0.12, -0.98...]  (Fast Nearest-Neighbor Search)
│
└── 3. The Map (Knowledge Graph)
    ├── Table: 'graph_nodes'             (File & Function Nodes)
    └── Table: 'graph_edges'             (Imports & Definitions)