==============================================================================
                        The DISMANTLER v2.1
          Modular Code Curation with Local AI Integration
==============================================================================

OVERVIEW
--------
The Dismantler is a federated orchestration system designed to surgically
dismantle monolithic codebases and redistribute their logic into a modular,
maintainable architecture. It provides an integrated workspace with local AI
support via Ollama for interactive code curation, iterative plan refinement,
and workflow-driven analysis.


ARCHITECTURE
------------
The system follows a three-layer federated model:

  1. BOOTSTRAPPER (src/app.py)
     System Console and Process Guard. Launches the backend engine
     followed by the UI framework. Provides thread-safe logging.

  2. UI FRAMEWORK (src/ui/)
     Tabbed workspace built on ttk.Notebook with:
     - 4-tab editor notebook (Original | Current | Diff | Context)
     - Chat panel with Ollama model integration and streaming
     - Browse, Search, Graph, and Patch lens views
     - Transformer Engine panel for monolith extraction
     - AI Plan Refinement panel with multi-pass iteration
     - Welcome screen when no files are open

  3. BACKEND ENGINE (src/backend/)
     Command center routing tasks through specialized controllers:
     - FileController:        Disk I/O with auto-archive to _backupBIN/
     - AIController:          Ollama inference and prompt formatting
     - TransformerController: Monolith extraction + AI refinement sessions
     - CurateController:      File -> AST -> Chunks -> Graph pipeline
     - ExportController:      Validated code export to disk

     All controllers expose a handle(schema) method and communicate
     through BackendEngine.execute_task({"system": "...", "action": "..."}).


4-TAB EDITOR NOTEBOOK
---------------------
Each workspace tab contains a 4-tab inner notebook:

  Tab 1: Original   Read-only baseline as loaded from disk
  Tab 2: Current    Editable scratchpad (default active tab)
  Tab 3: Diff       Read-only colored diff preview (green/red/cyan)
  Tab 4: Context    Diagnostic view (AST hierarchy, chunks, code metrics)

When a file is loaded, both Original and Current receive the content.
Edits happen in Current; Original stays frozen for reference.
Workflow results auto-route to Diff and Context tabs.


WORKFLOW ENGINE
---------------
The WorkflowEngine (src/backend/modules/workflow_engine.py) is a JSON-driven
sequential tool orchestrator. It executes a list of named steps, passing the
output of step N as input context for step N+1.

  Built-in step registry:
    curate         Runs the full curation pipeline on a file
    code_metrics   Calculates code quality metrics
    get_entities   Extracts AST entities and edges
    get_hierarchy  Builds a formatted AST tree
    ai_refinement  Sends the current plan through AI for improvement
    patch_preview  Generates a before/after diff preview

  Example workflow schema:
    {"name": "Default Curation", "steps": ["curate", "code_metrics"]}

  Custom steps can be registered at runtime via:
    WorkflowEngine.register_step("my_step", "controller", "action", {})


AI PLAN REFINEMENT
------------------
The refinement system allows an AI model to iteratively improve an extraction
plan over multiple inference passes with user control at each step.

  Backend: src/backend/modules/refinement_engine.py
    - RefinementSession tracks state: plan history, pass count, status
    - RefinementEngine orchestrates passes with phase-aware prompts:
        Pass 1:  Structural review (targets, blocks, single responsibility)
        Pass 2:  Dependency analysis (circular imports, shared utilities)
        Middle:  Iterative improvement (architecture, naming, edge cases)
        Final:   Validation and polish (parseable code, separation rules)

  UI: src/ui/modules/refinement_panel.py
    - Dual-pane layout: current plan (left) + streaming AI output (right)
    - Pass indicator bar with color-coded state per pass
    - Controls: Run Pass, Retry, Auto-Accept, Cancel
    - Model selector and configurable pass count (1-10)


MODULAR TOOLS
-------------
The system supports auto-discovered tools. Drop a .py file inheriting
from BaseTool into src/backend/tools/ and it loads at boot time.

  src/backend/tools/
    base_tool.py          Abstract base class (name, version, handle)
    boilerplate_tool.py   Template for creating new tools
    code_metrics_tool.py  Code quality analysis (LOC, complexity, etc.)

  Each tool must implement:
    name, version, description  Metadata properties
    initialize()                Setup (return True on success)
    handle(schema)              Action dispatch


QUICK START
-----------
  1. Run setup_env.bat to create the virtual environment
  2. Run run.bat to launch the application
  3. The System Console appears first, then the main workspace
  4. Use File > Open File (Ctrl+O) to load source code
  5. Edit in the "Current" tab; view the frozen original in "Original"
  6. Use the Chat panel to interact with local AI models
  7. Use Tools menu for analysis and extraction features


USE CASES
---------

  CASE 1: Inspect and curate a Python module
  -------------------------------------------
  1. File > Open File > select a .py file
  2. The file loads into Original (frozen) and Current (editable)
  3. Tools > AST Lens
     -> The Context tab switches to AST mode showing the full hierarchy:
        class MyClass  L1-45
          method __init__  L3-10
          method process   L12-30
  4. Tools > Run Default Workflow
     -> Runs "curate" then "code_metrics" sequentially
     -> Chunks appear in Context tab; diff appears in Diff tab
     -> Chat panel shows step-by-step progress

  CASE 2: Extract a monolithic file into modules
  -----------------------------------------------
  1. File > Open File > select a large monolithic .py file
  2. Tools > Transformer Engine (opens a new window)
  3. Click Browse and select the same file
  4. Choose strategy:
     - Auto-detect: uses heuristics to identify extractable blocks
     - Manual tags: looks for # <EXTRACT_TO:path> comments in source
  5. Click Analyze -> extraction plan appears in the preview pane
  6. Toggle "Dry-run" on for a safe preview, or off to write files
  7. Click Extract -> blocks are written to their target paths

  CASE 3: Refine an extraction plan with AI iteration
  ----------------------------------------------------
  1. Follow Case 2 through step 5 (Analyze generates a plan)
  2. Click "Refine with AI" -> the Refinement Panel opens
  3. Select an Ollama model from the dropdown, set passes to 3
  4. Click "Run Pass"
     -> Pass 1 streams AI output on the right pane (structural review)
     -> The left pane shows the current plan
  5. Review the AI's suggestions, then choose:
     - Approve:      Accept this pass, advance to pass 2
     - Retry:        Discard this pass, re-run with fresh inference
     - Auto-Accept:  Run all remaining passes automatically
     - Cancel:       Abort the refinement session
  6. After all passes complete, the refined plan is ready for extraction

  CASE 4: Use the chat for interactive AI assistance
  ---------------------------------------------------
  1. Open a file in the workspace
  2. The Chat panel (right sidebar) shows available Ollama models
  3. Type a question about the code:
     "What does the process() method do?"
  4. The AI receives sliding-window context around your cursor position
  5. Responses stream token-by-token into the chat history
  6. Chat > Clear Chat History to reset the conversation

  CASE 5: Create a custom analysis tool
  --------------------------------------
  1. Copy src/backend/tools/boilerplate_tool.py to a new file:
     src/backend/tools/my_analysis_tool.py
  2. Edit the class:
     - Set name = "My Analysis"
     - Set version = "1.0.0"
     - Implement handle(schema) with your analysis logic
     - Return {"status": "ok", "result": ...} or {"status": "error", ...}
  3. Restart the app -> the tool auto-loads at boot
  4. Tools > Refresh Models confirms it appears in the log

  CASE 6: Workflow-driven batch analysis
  --------------------------------------
  1. Open a file in the workspace
  2. Tools > Run Default Workflow
     -> Step 1/2: curate_file runs (AST parse, chunk indexing)
     -> Step 2/2: code_metrics runs (LOC, complexity, functions)
  3. Results auto-route to the editor notebook:
     - Diff tab:    shows before/after comparison if applicable
     - Context tab: shows chunks (from curation) or metrics (from analysis)
  4. Custom workflows can be triggered programmatically:
     tab.run_workflow(
         {"name": "Deep Analysis", "steps": ["curate", "get_entities", "code_metrics"]},
         model="llama3"
     )


PROJECT STRUCTURE
-----------------
  _TheDISMANTLER/
  |-- run.bat                   Launcher script
  |-- setup_env.bat             Environment setup
  |-- requirements.txt          Python dependencies
  |-- README.txt                This file
  |
  |-- _backupBIN/               Auto-archive directory
  |-- _logs/                    Application logs
  |-- _versioning-history/      Legacy archives
  |
  |-- src/
      |-- app.py                Bootstrapper / Process Guard
      |-- theme.py              Deep Space dark theme constants
      |
      |-- backend/
      |   |-- main.py           BackendEngine orchestrator
      |   |-- file_controller.py
      |   |-- ai_controller.py
      |   |-- transformer_controller.py
      |   |-- curate_controller.py
      |   |-- export_controller.py
      |   |
      |   |-- modules/
      |   |   |-- db_schema.py           SQLite schema and connection
      |   |   |-- sliding_window.py      Cursor-aware context window
      |   |   |-- ast_lens.py            AST hierarchy parser
      |   |   |-- ast_node_walker.py     Recursive entity/edge walker
      |   |   |-- query_engine.py        Safe SQL query interface
      |   |   |-- patch_engine.py        Whitespace-safe patching
      |   |   |-- transformer.py         Monolith extraction engine
      |   |   |-- refinement_engine.py   AI iterative plan refinement
      |   |   |-- workflow_engine.py     JSON-driven step orchestrator
      |   |
      |   |-- tools/
      |       |-- base_tool.py           Tool abstract base class
      |       |-- boilerplate_tool.py    Template for new tools
      |       |-- code_metrics_tool.py   Code quality analysis
      |
      |-- ui/
          |-- main_window.py     MainWindow + WelcomePanel
          |-- workspace_tab.py   4-tab editor + chat workspace
          |
          |-- modules/
              |-- _buttons.py           Reusable button widgets
              |-- _dropdowns.py         Dropdown / combobox
              |-- _panel.py             Panel container
              |-- text_editor.py        Line-numbered text editor
              |-- editor_notebook.py    4-tab notebook (Orig/Cur/Diff/Ctx)
              |-- chat_panel.py         Chat sidebar with streaming
              |-- model_selector.py     Ollama model picker
              |-- browser_lens.py       File browser Treeview
              |-- search_lens.py        Semantic search interface
              |-- graph_lens.py         Entity relationship view
              |-- patch_lens.py         Before/After diff view
              |-- transformer_panel.py  Extraction engine UI
              |-- refinement_panel.py   AI plan refinement UI


KEYBOARD SHORTCUTS
------------------
  Ctrl+N    New Tab
  Ctrl+O    Open File
  Ctrl+S    Save File
  Ctrl+W    Close Current Tab


CONSTRAINTS
-----------
  * Zero UI imports in backend/ (no tkinter, no messagebox)
  * Backend errors return {"status": "error", "message": "..."}
  * UI modules must be stateless (no database logic)
  * UI communicates with backend only via BackendEngine.execute_task()
  * No logic duplication across modules
  * Cross-controller access uses bind_engine() late-binding pattern


THEME
-----
  Deep Space / High-Contrast Dark Mode
  Background:  #1e1e2e     (bg)
  Surface 1:   #2a2a3e     (bg2)
  Surface 2:   #363650     (bg3)
  Text:        #cdd6f4     (fg)
  Text Dim:    #6c7086     (fg_dim)
  Accent:      #7c6af7
  Success:     #a6e3a1
  Warning:     #f9e2af
  Error:       #f38ba8
  Interface:   Segoe UI
  Code:        Consolas


LICENSE
-------
  MIT License - Copyright Jacob Lambert 2025
  See LICENSE.md for full text.
