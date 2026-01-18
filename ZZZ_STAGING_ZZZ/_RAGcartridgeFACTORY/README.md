# RAGcartridgeFACTORY

**A Deterministic Datasource Compiler for Local AI**

### Executive Summary

**RAGcartridgeFACTORY** is not a conversational agent. It is a strict *datasource compiler* that converts arbitrary client datasets (Filesystem, Web) into a portable, self-contained **Neural Cartridge** (SQLite).

The factory analyzes a source, compiles a human-checkable ingestion plan (Registry), and executes that plan to produce a cartridge containing verbatim data, structured hunks, vector indices, and a knowledge-graph projection. It adheres to the **Unified Neural Cartridge Format (UNCF)**.

---

### Core Principles (Non-Negotiable)

* **Factory, Not Agent:** This system does not "figure out" what to do. It executes a rigid State Machine: `Analyze`  `Plan`  `Commit`  `Refine`. 


* **Registry-Centered:** The Plan (Registry) is the source of truth. We never write to the database until the Plan is approved. 


* **Determinism First:** Verbatim truth is preserved. All derived artifacts (vectors, graph nodes) must reference a verbatim hunk. 


* **HITL by Design:** Human-In-The-Loop. Operators inspect the Registry before ingestion begins. 



---

### Architecture

The system is built on a modular Microservice architecture using Python and Tkinter.

* **The Spine (`src/orchestrator.py`):** Owns the State Machine, sequencing, and service delegation. It contains no UI code.
* **The Glue (`src/app.py`):** Bootstraps the application, initializes the Orchestrator, and wires the UI components.
* **The Organs (Microservices):**
* 
**Memory:** `_CartridgeServiceMS` (SQLite + sqlite-vec) 


* 
**Brain:** `_NeuralServiceMS` (Ollama Interface) 


* 
**Hands:** `_IntakeServiceMS` (Scanning) & `_RefineryServiceMS` (Processing) 


* 
**Eyes:** `_NeuralGraphViewerMS` (Physics-based visualization) 





---

### Quick Start

#### Prerequisites

* **Python 3.10+**
* **Ollama** running locally (default: `http://localhost:11434`) with `mxbai-embed-large` and `qwen2.5` (or similar models) pulled.

#### Installation

1. **Clone the repository:**
```bash
git clone <repo_url>
cd _RAGcartridgeFACTORY

```


2. **Initialize Environment:**
```bash
# Windows (using included script)
setup_env.bat

# Manual (Linux/Mac)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

```


3. **Launch the Factory:**
```bash
python src/app.py

```



---

### Workflow (The Assembly Line)

The UI exposes a strict 3-stage assembly line managed by the Orchestrator:

#### 1. SCAN (Analyze)

* **Input:** A source directory or URL.
* **Process:** The `_ScoutMS` recursively walks the target, identifying files and ignoring binary clutter.
* **Output:** An in-memory **Registry Plan**. This is visualized in the "Explorer" panel. No database writes occur yet.

#### 2. INGEST (Commit)

* **Input:** The approved Registry Plan.
* **Process:** The `_IntakeServiceMS` copies selected files into the Cartridge `files` table.
* **Output:** **Verbatim Storage**. Files are safely stored in the `sqlite` container with "RAW" status.

#### 3. REFINE (Process)

* **Input:** "RAW" files in the Cartridge.
* **Process:**
* 
**Chunking:** `_ChunkingRouterMS` routes files to specialists (AST for Python, Recursive for prose).


* **Embedding:** `_NeuralServiceMS` generates vectors for chunks.
* 
**Weaving:** `_RefineryServiceMS` builds graph nodes for classes, functions, and imports.




* **Output:** A fully refined Cartridge with searchable vectors and navigable graph topology.

---

### Directory Structure

```text
C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_RAGcartridgeFACTORY
├── src/
│   ├── app.py                  # Entry Point & UI Glue
│   ├── orchestrator.py         # State Machine & Logic Spine
│   └── microservices/
│       ├── _CartridgeServiceMS.py   # UNCF Schema Manager
│       ├── _IntakeServiceMS.py      # Scanner & Ingester
│       ├── _RefineryServiceMS.py    # Chunking & Graph Weaving
│       ├── _NeuralServiceMS.py      # Ollama Interface
│       ├── _NeuralGraphEngineMS.py  # Physics Visualization
│       ├── _WorkbenchLayoutMS.py    # UI Layout Engine
│       └── ... (Helper Services)
├── requirements.txt            # Dependencies (pygame, requests, sqlite-vec, etc.)
├── setup_env.bat               # Windows Quick-Start
└── README.md                   # This file

```

### Artifact Contracts

**The Cartridge (Output Artifact)**
A single `.sqlite` file containing:

1. 
**Manifest:** JSON metadata defining schema version, provenance, and embedding specs. 


2. 
**Files:** Verbatim content with VFS paths. 


3. 
**Chunks:** Semantic segments linked to parent files. 


4. 
**Vectors:** `sqlite-vec` embeddings for similarity search. 


5. 
**Graph:** Nodes and edges representing code structure and relationships. 



**License**
MIT License. Determinism is free.