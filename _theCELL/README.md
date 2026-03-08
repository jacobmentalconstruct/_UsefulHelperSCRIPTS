# _theCELL

A recursive, multi-window Tkinter workspace for running AI “cells” that can spawn child sessions, route content between active cells, stream model output in real time, and persist personas/prompts/settings in SQLite.

---

## What it does

This app launches a primary “cell” window (the shell + UI), backed by an orchestration hub (`Backend`). Each cell can:

- **Run streamed inference** (token-by-token) via the ingest engine service.
- **Spawn child cells** that inherit a summarized slice of context (“inherited_context”), forming a recursive workflow tree.
- **Route/push content to another live cell** using a global registry + signal bus routing guard (prevents infinite loops).
- **Persist “identity artifacts”** (personas, roles, system prompts, task prompts) to a local SQLite DB (`_db/app_internal.db`).
- **Flush “long-term memory”** through the factory into a vector destination (`long_term_history`) via a callback hook.

---

## Key architecture (mental map)

### app.py (Orchestrator / Shell bootstrap)
- Creates a **global** `CellRegistry()` used for naming + lineage.
- Initializes the first `Backend(registry=global_registry)`.
- Boots a `TkinterAppShellMS` and docks `CELL_UI(shell, backend)`.
- Wires global orchestration:
  - `cell_spawn_requested` → spawns a new Tk window + new Backend (child DNA hydration)
  - `register_cell` → keeps a local map of active cell backends
  - `push_to_nexus` → routes payloads across cells (with guard)

### backend.py (Logic hub for a single cell)
Owns the “service stack” and state:

- **State / identity**
  - `CellIdentity` + `CellRegistry` integration for lineage, names, and registry membership.
  - SQLite persistence under `_db/app_internal.db`.

- **Microservices**
  - `IngestEngineMS` (streamed generation)
  - `SignalBusMS` (event routing)
  - `CognitiveMemoryMS` (context window + summarizer + flush callback)
  - `HydrationFactoryMS` + specialists (`CodeFormatterMS`, `TreeMapperMS`, `VectorFactoryMS`)
  - `FeedbackValidationMS`, `ErrorNotifierMS`, `ConfigStoreMS`

- **Inference**
  - `process_submission()` creates a structured `artifact`, logs user input into memory, then starts a daemon thread for streaming output.
  - `_run_inference_thread()` emits tokens over the bus and finalizes the artifact.

- **Recursive workflow**
  - `spawn_child()` summarizes context and emits `SIGNAL_SPAWN_REQUESTED`.

---

## Requirements

This repo expects:
- Python 3.x
- Tkinter available (usually bundled with Python on Windows/macOS; varies on Linux)
- Your project’s `src/` package providing the referenced microservices and UI module:
  - `src.microservices.*`
  - `src.cell_identity`
  - `ui.py` (must define `CELL_UI`)

> Note: `IngestEngineMS.get_available_models()` and `generate_stream()` imply an external model runtime (commonly Ollama in this style of stack), but the exact dependency is defined inside your `src.microservices._IngestEngineMS`.

---

## Run

From the repo root (where your `src/` package is importable):

python -m app

Or if you’re running it as a script (depends on how your package is laid out):

python app.py

On first launch, the app will create:
- `_db/app_internal.db` for personas/prompts/etc.

---

## What to expect at runtime

- The main window title is `_theCELL [<cell_name>]` and uses a theme preference persisted under `theme_preference` (defaults to Dark).
- When a cell spawns a child:
  - A new session file name is generated like `session_YYYYMMDD_HHMMSS_micro.jsonl` (used as `memory_path`).
  - The child inherits a summarized context slice (`limit=10`).
- Closing a child window unregisters that cell and broadcasts registry updates to all remaining cells.

---

## Persistence

### SQLite (_db/app_internal.db)
Tables created/maintained:
- `personas` (name, role_text, sys_prompt_text, task_prompt_text, is_default, last_modified)
- `saved_roles`
- `saved_sys_prompts`
- `saved_task_prompts`

### Memory flush hook
`CognitiveMemoryMS` is configured with:
- a summarizer function (currently stubbed as truncation)
- a long-term ingest function that hydrates to `destination="long_term_history"`

---

## Repo structure (minimum expected)

.
├─ app.py
├─ backend.py
├─ ui.py                  # must define CELL_UI
└─ src/
   ├─ cell_identity.py
   └─ microservices/
      ├─ _TkinterAppShellMS.py
      ├─ _IngestEngineMS.py
      ├─ _SignalBusMS.py
      ├─ _CognitiveMemoryMS.py
      ├─ _HydrationFactoryMS.py
      ├─ _ConfigStoreMS.py
      ├─ _FeedbackValidationMS.py
      ├─ _ErrorNotifierMS.py
      ├─ _CodeFormatterMS.py
      ├─ _TreeMapperMS.py
      ├─ _VectorFactoryMS.py
      └─ microservice_std_lib.py

(Your actual repo may include more; the above is what `app.py` and `backend.py` directly import.)

---

## License

Add your preferred license here (MIT/Apache-2.0/etc).