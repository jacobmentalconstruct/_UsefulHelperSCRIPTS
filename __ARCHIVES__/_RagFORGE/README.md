# **\_RagFORGE: The Neural Cartridge Factory**

**"Manufacture portable, self-contained RAG databases for your AI agents."**

\_RagFORGE is a "Knowledge Foundry." It ingests raw data (Source Code, PDFs, Websites) and refines it into a **Unified Neural Cartridge (.db)**. These cartridges are portable SQLite databases that contain the raw archive, the semantic vector index, and the relational knowledge graph—everything an AI needs to understand a topic, in a single file.

## **🚀 Features**

* **Universal Ingestion:**  
  * **Filesystem:** Recursively scans folders, respecting .gitignore.  
  * **Documents:** Automatically extracts text from **PDFs** and **HTML**.  
  * **Web Crawler:** Spiders websites to a specified depth and converts them into a navigable Virtual File System (VFS).  
* **The Refinery (Background Daemon):**  
  * **Smart Chunking:** Uses AST parsing for Python (splitting by Class/Function) and semantic windows for prose/text.  
  * **Parallel Embedding:** High-speed vector generation using local LLMs (via Ollama).  
  * **Graph Weaving:** Automatically links files based on imports and definitions.  
* **The Cartridge (UNCF v1.0):**  
  * Portable .db file (SQLite).  
  * Contains **Source** (Text/Blob), **Vectors** (sqlite-vec), and **Graph** (Nodes/Edges).  
  * Self-describing Manifest.  
* **Visual Verification:**  
  * Force-Directed Graph Visualization.  
  * Real-time **Neural Test** to verify vector search relevance immediately.

## **🛠️ Installation**

1. **Prerequisites:**  
   * Python 3.10+  
   * [Ollama](https://ollama.ai/) running locally (ollama serve).  
   * Models pulled: ollama pull mxbai-embed-large (or your preferred embedder).  
2. **Setup:**  
   git clone \[https://github.com/yourusername/\_RagFORGE.git\](https://github.com/yourusername/\_RagFORGE.git)  
   cd \_RagFORGE  
   setup\_env.bat

3. **Run:**  
   \# Launch GUI  
   python \-m src.app

   \# Headless Mode (CLI)  
   python \-m src.app \--input "./my\_project" \--output "project\_brain.db"

## **💾 The Cartridge Contract (UNCF v1.0)**

Every cartridge produced by \_RagFORGE adheres to the **Unified Neural Cartridge Format**. This ensures any consuming agent (like \_LocalMIND) can instantly mount and query the brain.

\[ YOUR CARTRIDGE (.db) \]  
│  
├── 1\. The Archive (Verbatim Storage)   
│   └── Table: 'files'  
│       ├── vfs\_path: "src/main.py"      (Hierarchy)  
│       ├── content:  "import os..."     (Raw Text for LLM reading)  
│       └── blob:     \[Binary Data\]      (Original PDF/Image backup)  
│  
├── 2\. The Index (Semantic Search)  
│   ├── Table: 'chunks'                  (Text Segments)  
│   │   └── content: "def scan\_path..."  
│   └── Table: 'vec\_items'               (Mathematical Index)  
│       └── embedding: \[0.12, \-0.98...\]  (Fast Nearest-Neighbor Search)  
│  
└── 3\. The Map (Knowledge Graph)  
    ├── Table: 'graph\_nodes'             (File & Function Nodes)  
    └── Table: 'graph\_edges'             (Imports & Definitions)

### **1\. The Manifest (Boot Sector)**

Table: manifest  
Key-value store describing the cartridge's provenance and configuration.

* cartridge\_id: UUID4 unique identifier.  
* schema\_version: uncf\_v1.0.  
* created\_at\_utc: Timestamp of manufacture.  
* source\_root: Original path or URL of the source material.  
* ingest\_config: JSON record of which files were explicitly selected by the user.

### **2\. The Archive (Verbatim Storage)**

Table: files  
The "Physical" layer. Contains the raw data.

* vfs\_path: Portable, relative path (e.g., src/main.py or web/example.com/docs/intro.html).  
* content: UTF-8 Extracted Text (Input for the LLM).  
* blob\_data: Binary backup (Original PDF bytes, Images, etc.).  
* status: RAW (Needs processing), REFINED (Ready), or SKIPPED.

### **3\. The Index (Semantic Search)**

Tables: chunks, vec\_items  
The "Mathematical" layer. Enables similarity search.

* **chunks:** Text segments derived from the files.  
  * *Python:* Split by Class (class X) and Function (def y).  
  * *Docs:* Split by semantic window (e.g., 800 chars).  
* **vec\_items:** Virtual table (via sqlite-vec) storing the 1024-dimension embeddings.  
  * Queryable via KNN: WHERE embedding MATCH ? ORDER BY distance.

### **4\. The Map (Knowledge Graph)**

Tables: graph\_nodes, graph\_edges  
The "Relational" layer. Describes structure.

* **Nodes:** Represents Files (file), Web Pages (web), and Code Symbols (chunk).  
* **Edges:** Represents relationships like imports, defined\_in, or links\_to.

## **🖥️ Usage Guide**

### **The Workflow**

1. **Select Source:** Choose a local folder or paste a URL.  
2. **Scan:** \_RagFORGE builds a file tree. Adjust "Web Depth" for crawlers.  
3. **Ingest:** Select the files you want. Click **INGEST**.  
4. **Refine:** The background daemon will wake up, chunk the data, and embed it. Watch the "System Log."  
5. **Verify:** Go to **Neural Topology**, type a query (e.g., "Authentication System"), and click **Neural Test**. Relevant nodes will light up.

### **Keyboard Controls (Graph View)**

* **Scroll:** Zoom In/Out.  
* **Left Click:** Pan Camera.  
* **Left Click \+ Drag Node:** Move Node (Physics active).  
* **Double Click Node:** Focus & Zoom.

## **🧩 Architecture**

\[ \_RagFORGE App \]                 \[ External Services \]  
       │                                   │  
       ├── Intake Service  \<──(Scan)───\> Filesystem / Web  
       │        │                          │  
       ├── Refinery Service \<──(Embed)──\> Ollama (Localhost)  
       │        │  
       └── Cartridge Service ──\> \[ .db File (UNCF v1.0) \]

## **📄 License**

MIT License. Copyright (c) 2025 Jacob Lambert.