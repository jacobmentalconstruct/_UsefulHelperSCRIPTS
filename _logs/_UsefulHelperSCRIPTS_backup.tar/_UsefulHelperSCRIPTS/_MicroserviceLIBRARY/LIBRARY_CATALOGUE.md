# 📚 Microservice Library Card Catalogue
> **Generated**: 2025-12-23 08:50
> **Total Services**: 53
> **Swarm Configuration**: `4` Workers (`qwen2.5-coder:1.5b-cpu`), 1 Architect (`qwen2.5-coder:3b-cpu`)

## 🧠 System Architecture Overview
System analysis failed.

## 📇 Index
- **[ArchiveBotMS](#archivebotms)**: 
- **[AuthMS](#authms)**: ROLE: Simple authentication microservice providing username/password login
- **[CartridgeServiceMS](#cartridgeservicems)**: The Source of Truth.
- **[ChalkBoardMS](#chalkboardms)**: 
- **[ChunkingRouterMS](#chunkingrouterms)**: The Editor: A 'Recursive' text splitter.
- **[CodeChunkerMS](#codechunkerms)**: The Surgeon (Pure Python Edition): Splits code into semantic blocks
- **[CodeFormatterMS](#codeformatterms)**: The Architect.
- **[CodeGrapherMS](#codegrapherms)**: The Cartographer of Logic: Parses Python code to extract high-level 
- **[CodeJanitorMS](#codejanitorms)**: 
- **[CognitiveMemoryMS](#cognitivememoryms)**: The Hippocampus: Manages Short-Term (Working) Memory and orchestrates 
- **[ContentExtractorMS](#contentextractorms)**: The Decoder.
- **[ContextPackerMS](#contextpackerms)**: The Packer: Walks a directory and dumps all text-readable files 
- **[EnvironmentManagerMS](#environmentmanagerms)**: The Operator.
- **[ExplorerWidgetMS](#explorerwidgetms)**: A standalone file system tree viewer.
- **[HeuristicSumMS](#heuristicsumms)**: The Skimmer: Generates quick summaries of code/text files without AI.
- **[IngestEngineMS](#ingestenginems)**: The Heavy Lifter: Reads files, chunks text, fetches embeddings,
- **[IntakeServiceMS](#intakeservicems)**: The Vacuum. 
- **[IsoProcessMS](#isoprocessms)**: The Safety Valve: Spawns isolated processes with real-time logging feedback.
- **[LexicalSearchMS](#lexicalsearchms)**: The Librarian's Index: A lightweight, AI-free search engine.
- **[LibrarianMS](#librarianms)**: The Swarm Librarian.
- **[LibrarianMS](#librarianms)**: 
- **[LogViewMS](#logviewms)**: The Console: A professional log viewer widget.
- **[MonacoHostMS](#monacohostms)**: Hosts the Monaco Editor.
- **[NetworkLayoutMS](#networklayoutms)**: The Topologist: Calculates visual coordinates for graph nodes using
- **[NeuralGraphEngineMS](#neuralgraphenginems)**: ✨ This Python class implements a neural graph rendering engine using Pygame, pro
- **[NeuralGraphViewerMS](#neuralgraphviewerms)**: ✨ This Python class is a Tkinter-based UI component that hosts the neural graph 
- **[NeuralServiceMS](#neuralservicems)**: The Brain Interface: Orchestrates local AI operations via Ollama for inference a
- **[ProjectForgeMS](#projectforgems)**: The Blacksmith.
- **[PromptOptimizerMS](#promptoptimizerms)**: The Tuner: Uses an LLM to refine prompts or generate variations.
- **[PromptVaultMS](#promptvaultms)**: The Vault: A persistent SQLite store for managing, versioning, 
- **[PythonChunkerMS](#pythonchunkerms)**: Specialized Python AST Chunker.
- **[RefineryServiceMS](#refineryservicems)**: The Night Shift.
- **[RegexWeaverMS](#regexweaverms)**: The Weaver: A fault-tolerant dependency extractor.
- **[RoleManagerMS](#rolemanagerms)**: The Casting Director: Manages Agent Personas (Roles).
- **[SandboxManagerMS](#sandboxmanagerms)**: The Safety Harness: Manages a 'Sandbox' mirror of a 'Live' project.
- **[ScannerMS](#scannerms)**: The Scanner: Walks the file system, filters junk, and detects binary files.
- **[ScoutMS](#scoutms)**: The Scanner: Walks file systems OR crawls websites (Depth-Aware).
- **[SearchEngineMS](#searchenginems)**: The Oracle: Performs Hybrid Search (Vector Similarity + Keyword Matching).
- **[SemanticChunkerMS](#semanticchunkerms)**: Intelligent Code Splitter.
- **[ServiceRegistryMS](#serviceregistryms)**: The Tokenizer (v2): Scans a library of Python microservices and generates
- **[SpinnerThingyMaBobberMS](#spinnerthingymabobberms)**: The Visualizer: An interactive spinner widget.
- **[SysInspectorMS](#sysinspectorms)**: The Auditor: Gathers hardware and environment statistics.
- **[TasklistVaultMS](#tasklistvaultms)**: The Taskmaster: A persistent SQLite engine for hierarchical task management.
- **[TelemetryServiceMS](#telemetryservicems)**: The Nervous System.
- **[TextChunkerMS](#textchunkerms)**: The Butcher: A unified service for splitting text into digestible chunks
- **[ThoughtStreamMS](#thoughtstreamms)**: The Neural Inspector: A UI widget for displaying a stream of AI thoughts/logs
- **[TkinterAppShellMS](#tkinterappshellms)**: The Mother Ship.
- **[TkinterSmartExplorerMS](#tkintersmartexplorerms)**: The Navigator.
- **[TkinterThemeManagerMS](#tkinterthememanagerms)**: The Stylist: Holds the color palette and font settings.
- **[TkinterUniButtonMS](#tkinterunibuttonms)**: A generic button group that can merge ANY two actions.
- **[TreeMapperMS](#treemapperms)**: The Cartographer: Generates ASCII-art style directory maps.
- **[VectorFactoryMS](#vectorfactoryms)**: The Switchboard: Returns the appropriate VectorStore implementation
- **[WebScraperMS](#webscraperms)**: The Reader: Fetches URLs and extracts the main content using Readability.

---

### ArchiveBotMS
**File**: `_ArchiveBotMS.py`
**Description**: 

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `create_backup` | `source_path, output_dir, extra_exclusions, use_default_exclusions` |  |

---

### AuthMS
**File**: `_AuthMS.py`
**Description**: ROLE: Simple authentication microservice providing username/password login
      and signed session tokens.

INPUTS:
  - config: Optional configuration dict. Recognized keys:
      - 'secret_key': Secret used to sign tokens.

OUTPUTS:
  - Exposes `login` and `validate_session` endpoints for use in pipelines.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `login` | `username, password` | Attempt to log in with the provided username and password. |
| `validate_session` | `token` | Check if a serialized token is valid and not expired. |

---

### CartridgeServiceMS
**File**: `_CartridgeServiceMS.py`
**Description**: The Source of Truth.
Manages the Unified Neural Cartridge Format (UNCF v1.0).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `get_vector_dim` | `None` | Retrieves the expected vector dimension from the manifest spec. |
| `initialize_manifest` | `None` | Populates the boot sector with strict RagFORGE Cartridge Schema (UNCF) v1.1. |
| `set_manifest` | `key, value` | Upsert metadata key. |
| `get_manifest` | `key` | Retrieve metadata key. |
| `validate_cartridge` | `None` | Quality Control: Checks if the cartridge is Agent-Safe. |
| `store_file` | `vfs_path, origin_path, content, blob, mime_type, origin_type` | The Universal Input Method.  |
| `get_pending_files` | `limit` | Fetches files waiting for the Refinery. |
| `update_status` | `file_id, status, metadata` |  |
| `ensure_directory` | `vfs_path` | Idempotent insert for VFS directories. |
| `get_status_flags` | `None` | Returns key manifest status flags in a single call. |
| `list_files` | `prefix, status, limit` | Enumerate files in the cartridge (optionally filtered by VFS prefix and/or status). |
| `get_file_record` | `vfs_path` | Fetch a single file record by VFS path. |
| `list_directories` | `prefix` | Enumerate directories in the cartridge VFS. |
| `get_directory_tree` | `root` | Builds a nested directory tree starting at `root` ("" for full tree). |
| `get_status_summary` | `None` | Counts files by status and provides a quick cartridge overview. |
| `add_node` | `node_id, node_type, label, data` |  |
| `add_edge` | `source, target, relation, weight` |  |
| `search_embeddings` | `query_vector, limit` | Performs semantic search using sqlite-vec. |

---

### ChalkBoardMS
**File**: `_ChalkBoardMS.py`
**Description**: 

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `loaded` | `None` | Called by JS when the page is ready. |
| `log_action` | `action_name` | Called by JS when user interacts. |
| `update_sign` | `text, theme` | Updates the embedded HTML via JS injection. |
| `trigger_effect` | `effect` | Triggers CSS animations like 'shake'. |

---

### ChunkingRouterMS
**File**: `_ChunkingRouterMS.py`
**Description**: The Editor: A 'Recursive' text splitter.
It respects the natural structure of text (Paragraphs -> Sentences -> Words)
rather than just hacking it apart by character count.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `chunk_file` | `text, filename, max_size, overlap` | Extension-aware router. |

---

### CodeChunkerMS
**File**: `_CodeChunkerMS.py`
**Description**: The Surgeon (Pure Python Edition): Splits code into semantic blocks
(Classes, Functions) using indentation and regex heuristics.

Advantages: Zero dependencies. Works on any machine.
Disadvantages: Slightly less precise than Tree-Sitter for messy code.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `chunk_file` | `file_path, max_chars` | Reads a file and breaks it into logical blocks based on indentation. |

---

### CodeFormatterMS
**File**: `_CodeFormatterMS.py`
**Description**: The Architect.
Uses the WhitespaceEngine to enforce strict indentation rules, 
fixing 'staircase' formatting and mixed tabs/spaces.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `normalize_code` | `content, use_tabs, spaces` | Pure logic endpoint: Takes string, returns string + patch. |
| `format_file` | `file_path, use_tabs, spaces` | Filesystem endpoint: In-place repair of a file. |

---

### CodeGrapherMS
**File**: `_CodeGrapherMS.py`
**Description**: The Cartographer of Logic: Parses Python code to extract high-level 
symbols (classes, functions) and maps their 'Call' relationships.

Output: A graph structure (Nodes + Edges) suitable for visualization 
or dependency analysis.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `scan_directory` | `root_path` | Recursively scans a directory for .py files and builds the graph. |

---

### CodeJanitorMS
**File**: `_CodeJanitorMS.py`
**Description**: 

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `enforce_standards` | `dry_run` |  |

---

### CognitiveMemoryMS
**File**: `_CognitiveMemoryMS.py`
**Description**: The Hippocampus: Manages Short-Term (Working) Memory and orchestrates 
flushing to Long-Term Memory (Vector Store).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `add_entry` | `role, content, metadata` | Adds an item to working memory and persists it. |
| `get_context` | `limit` | Returns the most recent conversation history formatted for an LLM. |
| `get_full_history` | `None` | Returns the raw list of memory objects. |
| `commit_turn` | `None` | Signal that a "Turn" (User + AI response) is complete. |

---

### ContentExtractorMS
**File**: `_ContentExtractorMS.py`
**Description**: The Decoder.
A standalone utility microservice that separates the concern of 
document parsing from ingestion logic.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `get_health` | `None` | Returns the operational status and library availability. |
| `extract_text` | `blob, mime_type` | Main routing logic for extraction.  |

---

### ContextPackerMS
**File**: `_ContextPackerMS.py`
**Description**: The Packer: Walks a directory and dumps all text-readable files 
into a single monolithic text file with delimiters.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `pack_directory` | `root_path, output_filename, additional_excludes` | Walks the directory and writes file contents to the output file. |

---

### EnvironmentManagerMS
**File**: `_EnvironmentManagerMS.py`
**Description**: The Operator.
Finds the right Python interpreter (System vs Venv) and launches processes.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `resolve_python` | `project_path, config_override` | Priority: |
| `launch_script` | `project_path, script_rel_path, env_vars` |  |

---

### ExplorerWidgetMS
**File**: `_ExplorerWidgetMS.py`
**Description**: A standalone file system tree viewer.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `refresh_tree` | `None` |  |
| `get_selected_paths` | `None` |  |
| `process_gui_queue` | `None` |  |

---

### HeuristicSumMS
**File**: `_HeuristicSumMS.py`
**Description**: The Skimmer: Generates quick summaries of code/text files without AI.
Scans for high-value lines (headers, signatures, docstrings) and concatenates them.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `summarize` | `text, filename, max_chars` | Generates a summary string from the provided text. |

---

### IngestEngineMS
**File**: `_IngestEngineMS.py`
**Description**: The Heavy Lifter: Reads files, chunks text, fetches embeddings,
populates the Graph Nodes, and weaves Graph Edges.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `abort` | `None` |  |
| `check_ollama_connection` | `None` |  |
| `get_available_models` | `None` |  |
| `process_files` | `file_paths, model_name` |  |

---

### IntakeServiceMS
**File**: `_IntakeServiceMS.py`
**Description**: The Vacuum. 
Now supports two-phase ingestion:
1. Scan -> Build Tree (with .gitignore respect)
2. Ingest -> Process selected paths

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `get_health` | `None` | Returns the operational status of the IntakeServiceMS. |
| `ingest_source` | `source_path` | Headless/CLI Entry point: Scans and Ingests in one go. |
| `scan_path` | `root_path, web_depth` | Unified Scanner Interface. |
| `ingest_selected` | `file_list, root_path` | Ingests only the specific files passed in the list. |
| `save_persistence` | `root_path, checked_map` | Saves user selections into the Cartridge Manifest (Portable). |

---

### IsoProcessMS
**File**: `_IsoProcessMS.py`
**Description**: The Safety Valve: Spawns isolated processes with real-time logging feedback.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `execute` | `payload, config` |  |

---

### LexicalSearchMS
**File**: `_LexicalSearchMS.py`
**Description**: The Librarian's Index: A lightweight, AI-free search engine.

Uses SQLite's FTS5 extension to provide fast, ranked keyword search (BM25).
Ideal for environments where installing PyTorch/Transformers is impossible
or overkill.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `add_document` | `doc_id, text, metadata` | Adds or updates a document in the index. |
| `search` | `query, top_k` | Performs a BM25 Ranked Search. |

---

### LibrarianMS
**File**: `_LibrarianMS.py`
**Description**: The Swarm Librarian.
Spawns concurrent AI workers to scan the codebase and create a system manifest.
Optimized for Ryzen CPUs and 32GB RAM.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `generate_catalog` | `output_file` | Main entry point. Uses ThreadPoolExecutor for parallel processing. |

---

### LibrarianMS
**File**: `_LibrarianServiceMS.py`
**Description**: 

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `generate_catalog` | `output_file` |  |

---

### LogViewMS
**File**: `_LogViewMS.py`
**Description**: The Console: A professional log viewer widget.
Features:
- Thread-safe (consumes from a Queue).
- Message Consolidation ("Error occurred (x5)").
- Level Filtering (Toggle INFO/DEBUG/ERROR).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `clear` | `None` |  |
| `save` | `None` |  |

---

### MonacoHostMS
**File**: `_MonacoHostMS.py`
**Description**: Hosts the Monaco Editor.
This service spawns a GUI window and cannot be run in headless environments.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `launch` | `title, width, height, func` | Create and launch the window. |
| `set_save_callback` | `callback` | Sets the function to trigger when Ctrl+S is pressed in the editor. |
| `open_file` | `filepath, content` | Opens a file in the editor (must be called from a background thread or callback). |

---

### NetworkLayoutMS
**File**: `_NetworkLayoutMS.py`
**Description**: The Topologist: Calculates visual coordinates for graph nodes using
server-side algorithms (NetworkX). 
Useful for generating static map snapshots or pre-calculating positions 
to offload client-side rendering.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `calculate_layout` | `nodes, edges, algorithm` | Computes (x, y) coordinates for the given graph. |

---

### NeuralGraphEngineMS
**File**: `_NeuralGraphEngineMS.py`
**Description**: ✨ This Python class implements a neural graph rendering engine using Pygame, providing real-time visualization of complex relationships in a 2D force-directed graph. It includes functionalities for camera control, asset management, data manipulation, and physics simulation to ensure smooth rendering and interaction with the user.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `get_health` | `None` | Returns the operational status of the NeuralGraphEngineMS. |
| `resize` | `width, height` |  |
| `set_data` | `nodes, links` |  |
| `screen_to_world` | `sx, sy` |  |
| `get_node_at` | `sx, sy` |  |
| `handle_mouse_down` | `x, y` |  |
| `handle_mouse_move` | `x, y, is_dragging` |  |
| `handle_mouse_up` | `None` |  |
| `pan` | `dx, dy` |  |
| `zoom_camera` | `amount, mouse_x, mouse_y` |  |
| `highlight_nodes` | `node_ids` | Highlights specific nodes by ID. |
| `step_physics` | `None` |  |
| `get_image_bytes` | `None` |  |

---

### NeuralGraphViewerMS
**File**: `_NeuralGraphViewerMS.py`
**Description**: ✨ This Python class is a Tkinter-based UI component that hosts the neural graph engine and provides search/highlighting overlays. It includes features for searching, highlighting, and rendering graphs in a user-friendly interface.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `bind_services` | `cartridge, neural` |  |
| `run_search` | `event` |  |
| `load_from_db` | `db_path` | Loads graph data from SQLite. |
| `on_resize` | `event` |  |
| `on_double_click` | `event` |  |
| `on_click` | `event` |  |
| `on_release` | `event` |  |
| `on_drag` | `event` |  |
| `on_hover` | `event` |  |
| `on_zoom` | `amount` |  |
| `on_windows_scroll` | `event` |  |
| `animate` | `None` | The Heartbeat Loop. |

---

### NeuralServiceMS
**File**: `_NeuralServiceMS.py`
**Description**: The Brain Interface: Orchestrates local AI operations via Ollama for inference and embeddings.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `update_models` | `fast_model, smart_model, embed_model` | Called by the UI Settings Modal to change models on the fly. |
| `get_available_models` | `None` | Fetches list from Ollama for the UI dropdown. |
| `check_connection` | `None` | Pings Ollama to see if it's alive. |
| `get_embedding` | `text` | Generates a vector using the configured embedding model. |
| `request_inference` | `prompt, tier, format_json` | Synchronous inference request. |
| `process_parallel` | `items, worker_func` | Helper to run a function across many items using a ThreadPool. |

---

### ProjectForgeMS
**File**: `_ProjectForgeMS.py`
**Description**: The Blacksmith.
Creates directory structures, stamps out boilerplate code, and injects dependencies.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `forge_project` | `parent_path, project_name, dependencies, project_type` | Stamps out a new project folder. |

---

### PromptOptimizerMS
**File**: `_PromptOptimizerMS.py`
**Description**: The Tuner: Uses an LLM to refine prompts or generate variations.
Requires an 'inference_func' to be passed in the config, which accepts a string
and returns a string (simulating an LLM call).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `refine_prompt` | `draft_prompt, feedback` | Rewrites a prompt based on feedback. |
| `generate_variations` | `draft_prompt, num_variations, context_data` | Generates multiple versions of a prompt for testing. |

---

### PromptVaultMS
**File**: `_PromptVaultMS.py`
**Description**: The Vault: A persistent SQLite store for managing, versioning, 
and rendering AI prompts.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `create_template` | `slug, title, content, author, tags` | Creates a new prompt template with an initial version 1. |
| `add_version` | `slug, content, author` | Adds a new version to an existing template. |
| `get_template` | `slug` | Retrieves a full template with all history. |
| `render` | `slug, context` | Fetches the latest version and renders it with Jinja2. |
| `list_slugs` | `None` |  |

---

### PythonChunkerMS
**File**: `_PythonChunkerMS.py`
**Description**: Specialized Python AST Chunker.
Focuses exclusively on identifying classes and functions to preserve code logic.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `get_health` | `None` | Returns the operational status of the PythonChunkerMS. |
| `chunk` | `content` | Parses Python source into semantic CodeChunks. |

---

### RefineryServiceMS
**File**: `_RefineryServiceMS.py`
**Description**: The Night Shift.
Polls the DB for 'RAW' files and processes them into Chunks and Graph Nodes.

Graph Enrichment:
- Code: function/class nodes, resolved import edges when possible.
- Docs: section/chapter nodes for long-form text (md/txt/rst).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `get_health` | `None` | Returns the operational status of the RefineryServiceMS. |
| `process_pending` | `batch_size` | Main loop. Returns number of files processed. |

---

### RegexWeaverMS
**File**: `_RegexWeaverMS.py`
**Description**: The Weaver: A fault-tolerant dependency extractor.
Uses Regex to find imports, making it faster and more permissive
than AST parsers (works on broken code).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `extract_dependencies` | `content, language` | Scans code content for import statements. |

---

### RoleManagerMS
**File**: `_RoleManagerMS.py`
**Description**: The Casting Director: Manages Agent Personas (Roles).
Persists configuration for System Prompts, Attached KBs, and Memory Settings.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `create_role` | `name, system_prompt, description, kbs` | Creates a new Agent Persona. |
| `get_role` | `name_or_id` | Retrieves a role by Name or ID. |
| `list_roles` | `None` |  |
| `delete_role` | `name` |  |

---

### SandboxManagerMS
**File**: `_SandboxManagerMS.py`
**Description**: The Safety Harness: Manages a 'Sandbox' mirror of a 'Live' project.
Allows for safe experimentation, diffing, and atomic promotion of changes.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `init_sandbox` | `force` | Creates or resets the sandbox by mirroring the live project. |
| `reset_sandbox` | `None` | Discards all sandbox changes and re-syncs from live. |
| `get_diff` | `None` | Compares Sandbox vs Live. Returns added, modified, and deleted files. |
| `promote_changes` | `None` | Applies changes from Sandbox to Live. |

---

### ScannerMS
**File**: `_ScannerMS.py`
**Description**: The Scanner: Walks the file system, filters junk, and detects binary files.
Generates the tree structure used by the UI.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `is_binary` | `file_path` | Determines if a file is binary using two heuristics: |
| `scan_directory` | `root_path` | Recursively scans a directory and returns a JSON-compatible tree. |
| `flatten_tree` | `tree_node` | Helper to extract all valid file paths from a tree node  |

---

### ScoutMS
**File**: `_ScoutMS.py`
**Description**: The Scanner: Walks file systems OR crawls websites (Depth-Aware).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `is_binary` | `file_path` |  |
| `scan_directory` | `root_path, web_depth` | Main Entry Point. |
| `flatten_tree` | `tree_node` |  |

---

### SearchEngineMS
**File**: `_SearchEngineMS.py`
**Description**: The Oracle: Performs Hybrid Search (Vector Similarity + Keyword Matching).

Architecture:
1. Vector Search: Uses sqlite-vec (vec0) for fast nearest neighbor search.
2. Keyword Search: Uses SQLite FTS5 for BM25-style text matching.
3. Reranking: Combines scores using Reciprocal Rank Fusion (RRF).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `search` | `db_path, query, limit` | Main entry point. Returns a list of results sorted by relevance. |

---

### SemanticChunkerMS
**File**: `_SemanticChunkerMS.py`
**Description**: Intelligent Code Splitter.
Parses source code into logical units (Classes, Functions) 
rather than arbitrary text windows.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `chunk_file` | `content, filename` | Splits file content into chunks. |

---

### ServiceRegistryMS
**File**: `_ServiceRegistryMS.py`
**Description**: The Tokenizer (v2): Scans a library of Python microservices and generates
standardized JSON 'Service Tokens'.
Feature: Hybrid AST/Regex parsing for maximum robustness.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `scan` | `save_to` |  |

---

### SpinnerThingyMaBobberMS
**File**: `_SpinnerThingyMaBobberMS.py`
**Description**: The Visualizer: An interactive spinner widget.
Useful for "Processing..." screens or OBS overlays.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `launch` | `None` | Starts the Tkinter main event loop. |
| `handle_keypress` | `event` |  |
| `get_neon_color` | `offset` |  |
| `draw_arc` | `cx, cy, radius, width, start, extent, color` |  |
| `animate` | `None` |  |

---

### SysInspectorMS
**File**: `_SysInspectorMS.py`
**Description**: The Auditor: Gathers hardware and environment statistics.
Supports: Windows (WMIC), Linux (lscpu/lspci), and macOS (sysctl/system_profiler).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `generate_report` | `None` | Runs the full audit and returns a formatted string report. |

---

### TasklistVaultMS
**File**: `_TasklistVaultMS.py`
**Description**: The Taskmaster: A persistent SQLite engine for hierarchical task management.
Supports infinite nesting of sub-tasks and status tracking.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `create_list` | `name` | Creates a new task list and returns its ID. |
| `get_lists` | `None` | Returns metadata for all task lists. |
| `add_task` | `list_id, content, parent_id` | Adds a task (or sub-task) to a list. |
| `update_task` | `task_id, content, status, result` | Updates a task's details. |
| `get_full_tree` | `list_id` | Fetches a list and reconstructs the full hierarchy of tasks. |
| `delete_list` | `list_id` |  |

---

### TelemetryServiceMS
**File**: `_TelemetryServiceMS.py`
**Description**: The Nervous System.
Watches the thread-safe LogQueue and updates the GUI Panels.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `get_health` | `None` | Returns the operational status of the TelemetryServiceMS. |
| `start` | `None` | Begins the GUI update loop. |
| `ping` | `None` | Allows an agent to verify the pulse of the UI loop. |

---

### TextChunkerMS
**File**: `_TextChunkerMS.py`
**Description**: The Butcher: A unified service for splitting text into digestible chunks
for RAG (Retrieval Augmented Generation).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `chunk_by_chars` | `text, chunk_size, chunk_overlap` | Standard Sliding Window. Best for prose/documentation. |
| `chunk_by_lines` | `text, max_lines, max_chars` | Line-Preserving Chunker. Best for Code. |

---

### ThoughtStreamMS
**File**: `_ThoughtStreamMS.py`
**Description**: The Neural Inspector: A UI widget for displaying a stream of AI thoughts/logs
visualized as 'bubbles' with sparklines.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `add_thought_bubble` | `filename, chunk_id, content, vector_preview, color` | Mimics the 'InspectorFrame' from your React code. |

---

### TkinterAppShellMS
**File**: `_TkinterAppShellMS.py`
**Description**: The Mother Ship.
Owns the Tkinter Root. All other UI microservices dock into this.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `launch` | `None` | Ignition sequence start. |
| `get_main_container` | `None` | Other services call this to know where to .pack() themselves. |
| `shutdown` | `None` |  |

---

### TkinterSmartExplorerMS
**File**: `_TkinterSmartExplorerMS.py`
**Description**: The Navigator.
A TreeView widget that expects standard 'Node' dictionaries (name, type, children).

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `load_data` | `data` | Ingests a dictionary tree (like from _ScoutMS or _TreeMapperMS). |

---

### TkinterThemeManagerMS
**File**: `_TkinterThemeManagerMS.py`
**Description**: The Stylist: Holds the color palette and font settings.
All UI components query this service to decide how to draw themselves.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `get_theme` | `None` |  |
| `update_key` | `key, value` |  |

---

### TkinterUniButtonMS
**File**: `_TkinterUniButtonMS.py`
**Description**: A generic button group that can merge ANY two actions.
Pass the visual/functional definitions in via the config objects.

---

### TreeMapperMS
**File**: `_TreeMapperMS.py`
**Description**: The Cartographer: Generates ASCII-art style directory maps.
Useful for creating context snapshots for LLMs.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `generate_tree` | `root_path, additional_exclusions, use_default_exclusions` |  |

---

### VectorFactoryMS
**File**: `_VectorFactoryMS.py`
**Description**: The Switchboard: Returns the appropriate VectorStore implementation
based on configuration.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `create` | `backend, config` | :param backend: 'faiss' or 'chroma' |

---

### WebScraperMS
**File**: `_WebScraperMS.py`
**Description**: The Reader: Fetches URLs and extracts the main content using Readability.
Strips ads, navbars, and boilerplate to return clean text for LLMs.

| Endpoint | Inputs | Summary |
| :--- | :--- | :--- |
| `scrape` | `url` | Synchronous wrapper for fetching and cleaning a URL. |

---
