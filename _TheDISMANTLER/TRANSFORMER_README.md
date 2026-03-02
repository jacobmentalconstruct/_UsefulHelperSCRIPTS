# The Modular Transformation Engine

## Overview

The **Modular Transformation Engine** is a "Strangler Fig" extraction system that surgically disassembles monolithic Python files and redistributes their logic into the Dismantler v2.0 federated architecture.

It automates the process of:
- **Parsing** a large file and understanding its structure
- **Classifying** code blocks by domain (UI, backend, database, algorithms)
- **Extracting** related code into modular units
- **Resolving** dependencies and imports
- **Preventing** duplication through intelligent deduplication
- **Ensuring** architectural constraints (stateless UI, headless backend)

---

## Architecture

### Three-Layer Transformation Pipeline

```
┌─────────────────────────────────────────────┐
│  Phase 1: Semantic Analysis                 │
│  - Parse AST                                │
│  - Identify classes, functions, patterns    │
│  - Map dependencies                         │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│  Phase 2: Surgical Extraction               │
│  - Tag blocks for extraction                │
│  - Auto-detect candidates                   │
│  - Check for duplicates                     │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│  Phase 3: Integrity & Synthesis             │
│  - Resolve imports                          │
│  - Add missing dependencies                 │
│  - Verify constraints                       │
│  - Write refactored files                   │
└─────────────────────────────────────────────┘
```

### Core Components

1. **`transformer.py`** – The Parsing Orchestrator
   - `MonolithTransformer` class
   - AST analysis and dependency mapping
   - Extraction strategy coordination

2. **`transformer_controller.py`** – High-level Interface
   - Controller for BackendEngine integration
   - Workflow orchestration
   - Reporting and guidance

3. **`transformer_panel.py`** – UI Component
   - Interactive transformer interface
   - File selection, strategy choice, plan preview
   - Integrated into Tools menu

---

## Usage

### Method 1: Auto-Detection (Recommended for Beginners)

The transformer uses intelligent heuristics to automatically identify extraction candidates:

1. **Open Tools > Transformer Engine** from the menu
2. **Select a file** to transform
3. **Choose "Auto-detect"** strategy
4. **Click Analyze** to preview the extraction plan
5. **Check "Dry-run"** to preview without writing
6. **Click Extract** to execute

The auto-detector classifies code by:
- **Tkinter patterns** → `src/ui/modules/`
- **Controller classes** → `src/backend/*_controller.py`
- **Database logic** → `src/backend/modules/db_schema.py`
- **Pure algorithms** → `src/backend/modules/`

### Method 2: Manual Tagging (Maximum Control)

For precise control, manually annotate your monolith with extraction tags:

```python
# datastore.py

# <EXTRACT_TO: src/backend/models_controller.py>
class ModelsController:
    def list_models(self):
        """Fetch Ollama models."""
        pass

    def generate(self, model, prompt):
        """Run inference."""
        pass
# </EXTRACT_TO>

# <EXTRACT_TO: src/backend/modules/utils.py>
def cosine_similarity(a, b):
    """Pure vector math utility."""
    pass
# </EXTRACT_TO>

class DatabaseManager:
    """Keep this - no tag means don't extract."""
    pass
```

Then:

1. **Open Tools > Transformer Engine**
2. **Select the tagged file**
3. **Choose "Manual tags"** strategy
4. **Click Analyze** to see the guide
5. **Click Extract**

---

## Classification Rules

### Automatic Classification Heuristics

The transformer uses these rules to decide where code should go:

| Code Pattern | Target Destination | Constraint |
|---|---|---|
| `import tkinter`, `tk.Frame`, `ttk.*` | `src/ui/modules/[name].py` | Must be stateless |
| `class *Controller` | `src/backend/[name]_controller.py` | Must handle domain logic |
| `sqlite`, `execute`, `cursor` | `src/backend/modules/db_schema.py` | Append to schema |
| `def foo():` (no self) | `src/backend/modules/[name].py` | Pure functions only |
| Mixed UI+DB logic | **Review required** | Needs splitting |

### Architectural Constraints

✅ **DO:**
- Put all database queries in `db_schema.py` or `*_controller.py`
- Keep UI modules free of `sqlite3`, `requests`, business logic
- Import `theme` in UI modules for consistency
- Use `BackendEngine.execute_task()` for UI↔Backend communication

❌ **DON'T:**
- Import `tkinter` in backend modules
- Store app state in UI modules
- Mix database and UI logic in the same file
- Create circular dependencies between modules

---

## Workflow Example: Refactoring `legacy_datastore.py`

### Step 1: Analyze

```
$ Open Transformer Engine
$ Select: src/_legacy-logic/legacy_datastore.py
$ Click Analyze
```

Output:
```
Extraction Guide
==============

File: legacy_datastore.py
Classes found: 3
Functions found: 12

Recommended Tags:

# Class: DatastoreController
# → Suggested: src/backend/datastore_controller.py

# Class: QueryHelper
# → Suggested: src/backend/modules/db_schema.py

# Function: normalize_text()
# → Suggested: src/backend/modules/utils.py
```

### Step 2: Tag (Optional)

If using auto-detect, skip this. For manual:

```python
# <EXTRACT_TO: src/backend/datastore_controller.py>
class DatastoreController:
    def save(self, data):
        # database operations
        pass
# </EXTRACT_TO>
```

### Step 3: Preview

```
$ Enable "Dry-run"
$ Click Extract
```

Preview shows:
```
Writing to src/backend/datastore_controller.py
  - DatastoreController (class)

Writing to src/backend/modules/db_schema.py
  - QueryHelper (class) → DUPLICATE DETECTED

Skipping: QueryHelper already exists
```

### Step 4: Execute

```
$ Disable "Dry-run"
$ Click Extract
```

Files are now written to their destinations.

---

## Advanced Features

### Deduplication

The transformer checks for duplicate logic:

```python
# If this function already exists:
def normalize_text(s):
    return s.strip().lower()

# And you extract the same logic:
# <EXTRACT_TO: src/backend/modules/utils.py>
def normalize_text(s):
    return s.strip().lower()
# </EXTRACT_TO>

# Result: Skipped - normalized content hash matches
#         existing definition in src/backend/modules/utils.py
```

### Dependency Resolution

Extracts automatically include necessary imports:

```python
# Original code:
class VectorStore:
    def __init__(self):
        self.db = get_connection()  # From db_schema.py
        self.theme = THEME          # From theme.py

# After extraction, the new file includes:
# from backend.modules.db_schema import get_connection
# from theme import THEME
```

### Integrity Checks

The engine verifies:

- ✓ No circular imports
- ✓ All external dependencies resolvable
- ✓ No UI modules importing tkinter twice
- ✓ No backend modules importing tkinter at all
- ✓ All class/function names valid Python identifiers

---

## Troubleshooting

### "No models found" / "Connection Error"

The transformer couldn't parse the file. Check:
- Is it valid Python syntax?
- Are all docstrings properly closed?
- Does it have circular imports that confuse the parser?

**Fix:** Open the file in `src/ui/` and manually fix syntax errors.

### "Duplicate detected"

The transformer found similar code already exists:
- Check the suggested location in the message
- Decide: is it truly identical? If so, skip the extraction
- Or modify one version to avoid redundancy

**Fix:** Look at the existing file and decide if you need the new version.

### "Unresolved imports"

A block references external packages that aren't in `requirements.txt`:
- Check what was imported in the original monolith
- Add missing packages to `requirements.txt`
- Re-run extraction

**Fix:** `pip install [package]` and add to requirements.txt

---

## API Reference

### TransformerPanel (UI Component)

```python
from ui.modules.transformer_panel import TransformerPanel

# Create a transformer window
panel = TransformerPanel(parent, backend=backend_engine)
# Opens an interactive dialog
```

### TransformerController (Backend)

```python
from backend.transformer_controller import TransformerController

controller = TransformerController(project_root, log)

# Analyze a file
analysis = controller.analyze_monolith("path/to/file.py")

# Extract with manual tags
result = controller.extract_with_tags("path/to/file.py", dry_run=True)

# Extract with auto-detection
result = controller.extract_auto("path/to/file.py", dry_run=True)

# Generate extraction guide
guide = controller.generate_extraction_guide("path/to/file.py")
```

### MonolithTransformer (Core Engine)

```python
from backend.modules.transformer import MonolithTransformer

transformer = MonolithTransformer(project_root, log)

# Parse structure
summary = transformer.parse_file("monolith.py")
# Returns: {classes: [...], functions: [...], imports: [...]}

# Extract tagged blocks
blocks = transformer.extract_tagged_blocks("monolith.py")

# Auto-detect blocks
blocks = transformer.auto_detect_blocks("monolith.py")

# Write blocks to files
result = transformer.write_blocks(blocks, dry_run=False)
# Returns: {written: [...], skipped: [...], duplicates: [...]}
```

---

## Best Practices

### 1. Start with Analysis
Always run **Analyze** first to understand the file structure before extracting.

### 2. Use Dry-Run
Always check **Dry-run** to preview changes before actually writing files.

### 3. Keep Files Small
Target 200-500 lines per extracted file. Smaller units are easier to test and maintain.

### 4. Preserve Intent
Don't extract code that's highly interdependent. Keep related logic together.

### 5. Test After Extraction
After extraction, verify:
```bash
cd src
python -m app  # Should start without import errors
```

### 6. Review Imports
Check generated imports match the actual dependencies. Remove unused imports manually.

---

## Limitations & Future Work

**Current Limitations:**
- Doesn't handle nested classes with deep hierarchies
- Comments are lost during extraction (use docstrings instead)
- Can't resolve dynamic imports or `importlib` patterns
- No refactoring of variable names across extracted code

**Future Enhancements:**
- Interactive dependency graph visualization
- Multi-file extraction (extract across multiple source files at once)
- Automatic test file generation
- Custom classification rules via config file
- AST-based comment preservation

---

## Examples

### Example 1: Extract a Tkinter Widget Class

```python
# Original monolith
class CustomDataGrid(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.tree = ttk.Treeview(self)
        self.tree.pack()

    def add_row(self, data):
        self.tree.insert('', 'end', values=data)

# Tag it:
# <EXTRACT_TO: src/ui/modules/data_grid.py>
# ... (class code)
# </EXTRACT_TO>

# Result: New file src/ui/modules/data_grid.py
# Includes: import tkinter as tk, from tkinter import ttk, from theme import THEME
```

### Example 2: Extract Database Helpers

```python
# <EXTRACT_TO: src/backend/modules/db_schema.py>
def get_model_by_id(db, model_id):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM models WHERE id=?", (model_id,))
    return cursor.fetchone()
# </EXTRACT_TO>

# Result: Function added to db_schema.py with proper import resolution
```

### Example 3: Auto-Detect Controller Classes

```python
# In monolith.py
class ChatController:
    def send_message(self, msg):
        pass

    def get_history(self):
        pass

# Run auto-detect → suggests src/backend/chat_controller.py
# Auto-detect recognizes "Controller" suffix → backend domain
```

---

## Getting Help

For issues or questions:
1. Check the troubleshooting section above
2. Review generated error messages in the transformer panel
3. Look at the extraction guide for hints
4. Inspect output files to verify correctness

---

**Version:** 1.0
**Last Updated:** 2026-03-02
