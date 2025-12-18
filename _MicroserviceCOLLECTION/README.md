

Include a README.md with each microservice in the format seen below (adhere to the format it is concise to save context window space with AI agents):
# [SERVICE_NAME] v[VERSION]
> [ONE_SENTENCE_ROLE]

## Setup
* **Deps:** `pip install -r requirements.txt`
* **Env:** `PYTHONPATH=..` (Must find `microservice_std_lib.py`)
* **Run:** `python app.py`

## Specs
* **Port:** [DEFAULT_PORT]
* **Input:** [PRIMARY_INPUT]
* **Output:** [PRIMARY_OUTPUT]

Here is a comprehensive `README.md` cataloging your microservices. This document provides the Name, Purpose (Role), and Description for each service based on their internal source code metadata.

# Microservice Collection Catalogue

> A directory of AI-discoverable services providing specialized utility for the Cortex architecture.

---

### 🌐 API & Networking

* 
**APIGateway** (v2.0.0) 


* 
**Purpose:** Expose a local Python object as an HTTP API surface.


* 
**Description:** Dynamically binds Python callables to REST endpoints and handles inbound API routing, health checks, and CORS configuration.





### 📂 Filesystem & Backups

* 
**ArchiveBot** (v1.1.0) 


* 
**Purpose:** Create timestamped compressed .tar.gz backups of directory trees.


* 
**Description:** Automates directory compression with built-in exclusions for common development artifacts like `node_modules` and `venv`.




* 
**ContextAggregator** (v1.0.0) 


* 
**Purpose:** Flatten a project folder into a single readable text file.


* 
**Description:** Compiles project files into a single text dump for easy ingestion by AI models, filtering out binary files and common ignored directories.




* 
**FingerprintScanner** (v1.0.0) 


* 
**Purpose:** Generate a deterministic SHA-256 fingerprint of a directory tree.


* 
**Description:** Acts as a "Detective" by scanning a project and returning a comprehensive state object containing file hashes and a global Merkle Root for integrity verification.





### 🔐 Security & Management

* 
**Auth** (v1.0.0) 


* 
**Purpose:** Manage user authentication and signed session tokens.


* 
**Description:** Provides a simplified in-memory authentication system for login and session validation using signed tokens.




* 
**RoleManager** (v1.0.0) 


* 
**Purpose:** Manage Agent Personas (Roles), System Prompts, and Memory Settings.


* 
**Description:** Acts as a "Casting Director" by persisting configurations for system prompts, attached knowledge bases, and memory policies.





### 🧠 Logic & Knowledge Analysis

* 
**CodeChunker** (v1.0.0) 


* 
**Purpose:** Split code into semantic blocks (Classes, Functions) using indentation and regex heuristics.


* 
**Description:** A zero-dependency "Surgeon" that breaks down code into logical fragments based on structural boundaries.




* 
**CodeGrapher** (v1.0.0) 


* 
**Purpose:** Parse Python code to extract symbols and call relationships.


* 
**Description:** The "Cartographer of Logic" that generates a graph structure of nodes and edges suitable for dependency analysis and visualization.




* 
**HeuristicSum** (v1.0.0) 


* 
**Purpose:** Generate quick summaries of code or text files using regex heuristics without AI.


* 
**Description:** Scans for high-value lines such as headers, function signatures, and docstrings to provide a rapid skimmer-style overview.




* 
**CognitiveMemory** (v1.0.0) 


* 
**Purpose:** Manage Short-Term (Working) Memory and orchestrate flushing to Long-Term Memory.


* 
**Description:** Functions as the "Hippocampus" of the system, handling active conversation history and consolidating it into permanent storage.





### 📊 Data & Versioning

* 
**DiffEngine** (v1.0.0) 


* 
**Purpose:** Implement hybrid versioning (Head + Diff History) for file content.


* 
**Description:** The "Timekeeper" that maintains current content in a fast-access "HEAD" while storing historical deltas for audit trails.




* 
**LexicalSearch** (v1.0.0) 


* 
**Purpose:** Provide lightweight BM25 keyword search using SQLite FTS5.


* 
**Description:** An AI-free search engine that offers fast, ranked keyword searching without the overhead of heavy vector models.





### 🛠️ Runtime & UI

* 
**ExplorerWidget** (v1.0.0) 


* 
**Purpose:** A standalone file system tree viewer widget.


* 
**Description:** A Tkinter-based UI component for exploring directories and managing checked-folder states.




* 
**GitPilot** (v1.0.0) 


* 
**Purpose:** Provide a GUI panel for Git operations.


* 
**Description:** A professional interface for common Git workflows including staging, committing, pushing, and pulling.




* 
**GraphEngine** (v1.0.0) 


* 
**Purpose:** Provide an interactive 2D Force-Directed Graph Visualizer.


* 
**Description:** A physics-driven visualization engine powered by Pygame and Tkinter for viewing complex relationships.




* 
**IsoProcess** (v1.0.0) 


* 
**Purpose:** Spawn isolated processes with real-time logging feedback.


* 
**Description:** A "Safety Valve" that executes heavy or risky payloads in child processes while bridging logs back to the main application.