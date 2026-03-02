# Modular Tools System

## Overview

The **Modular Tools System** allows you to extend Dismantler with custom functionality. Tools are:

- **Auto-discovered** – Drop a `.py` file in `src/backend/tools/` and it's loaded automatically
- **Standardized** – All tools inherit from `BaseTool` with a consistent interface
- **Isolated** – Each tool is independent and can be developed/tested separately
- **Accessible** – Called via `BackendEngine.execute_task()` from anywhere in the system

---

## Architecture

```
src/backend/tools/
├── __init__.py                   # Package marker
├── base_tool.py                  # BaseTool abstract class
├── boilerplate_tool.py           # Template for new tools
├── code_metrics_tool.py          # Example: code analysis
└── my_custom_tool.py             # Your tools go here
```

### How It Works

1. **Auto-discovery at boot:**
   - BackendEngine scans `src/backend/tools/` for `.py` files
   - Finds all `BaseTool` subclasses
   - Instantiates and initializes each tool
   - Registers them in the `controllers` dict

2. **Execution via schema:**
   ```python
   result = backend.execute_task({
       "system": "code_metrics",    # Tool name (lowercase, underscores)
       "action": "analyze",         # Tool-specific action
       "file": "/path/to/file.py"   # Custom parameters
   })
   ```

3. **Response format:**
   ```python
   {
       "status": "ok" | "error",
       "message": "Human-readable message",
       ... other fields depend on tool
   }
   ```

---

## Creating a New Tool

### Step 1: Copy the Boilerplate

```bash
cp src/backend/tools/boilerplate_tool.py src/backend/tools/my_new_tool.py
```

### Step 2: Customize the Class

```python
from backend.tools.base_tool import BaseTool
from typing import Dict, Any

class MyNewTool(BaseTool):
    """Description of what your tool does."""

    # ── Metadata ────────────────────────────
    name = "My New Tool"
    version = "1.0.0"
    description = "Detailed description here"
    tags = ["category", "feature"]
    requires = ["requests", "numpy"]  # External dependencies

    def initialize(self) -> bool:
        """Setup when tool loads."""
        self.log(f"Initializing {self.name}...")
        # Check dependencies, set up connections, etc.
        return super().initialize()

    def handle(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point."""
        action = schema.get("action")

        if action == "my_action":
            return self._my_action(schema)
        else:
            return self.error(f"Unknown action: {action}")

    def _my_action(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Implement your logic here."""
        # Validate input
        ok, err = self.validate_schema(schema, ["required_field"])
        if not ok:
            return self.error(err)

        # Do work
        result = self._do_something(schema.get("required_field"))

        # Return success
        return self.success(
            message="Action completed",
            result=result
        )

    def _do_something(self, input_data):
        """Helper method for your logic."""
        return f"Processed: {input_data}"
```

### Step 3: Test It

```python
# In your code or interactive shell:
result = backend.execute_task({
    "system": "my_new_tool",
    "action": "my_action",
    "required_field": "test data"
})
print(result)
# {"status": "ok", "message": "...", "result": "..."}
```

### Step 4: Done!

Your tool is now loaded automatically. No additional registration needed.

---

## BaseTool API Reference

### Metadata (required)

```python
class MyTool(BaseTool):
    name = "Tool Name"              # str, displayed in UI
    version = "1.0.0"               # str, semantic versioning
    description = "What it does"    # str, one-liner
    tags = ["tag1", "tag2"]         # List[str], for categorization
    requires = ["requests"]         # List[str], external packages
```

### Methods (override as needed)

```python
# Called once when tool loads
def initialize(self) -> bool:
    # Check dependencies, setup connections
    # Return False to fail loading
    return super().initialize()

# Main handler - you must implement this
def handle(self, schema: Dict[str, Any]) -> Dict[str, Any]:
    # Process the schema and return results
    pass

# Called when tool is unloaded
def shutdown(self):
    # Cleanup connections, save state, etc.
    pass
```

### Helper Methods

```python
# Validate schema has required keys
ok, err = self.validate_schema(schema, ["field1", "field2"])
if not ok:
    return self.error(err)

# Check if external packages are installed
ok, missing = self.validate_dependencies()
if not ok:
    return self.error(f"Missing: {missing}")

# Build success response
return self.success(
    message="Done",
    result=data,
    extra_field="value"
)

# Build error response
return self.error(
    "Something went wrong",
    error_code=400
)

# Log a message
self.log("Message to log")

# Get tool metadata
metadata = self.get_metadata()
# Returns: {name, version, description, tags, requires, initialized}
```

---

## Example Tools

### Example 1: Code Metrics Tool

Location: `src/backend/tools/code_metrics_tool.py`

This tool analyzes Python files and returns:
- Line counts (code, comments, blank)
- Function/class counts
- Complexity estimates
- Comment ratio

**Usage:**
```python
result = backend.execute_task({
    "system": "code_metrics",
    "action": "analyze",
    "file": "src/app.py"
})

# Returns:
# {
#     "status": "ok",
#     "metrics": {
#         "total_lines": 150,
#         "code_lines": 120,
#         "comment_lines": 20,
#         "functions": 5,
#         "classes": 2,
#         "complexity_rating": "Moderate"
#     }
# }
```

### Example 2: Boilerplate Tool

Location: `src/backend/tools/boilerplate_tool.py`

A minimal working tool that demonstrates:
- Metadata definition
- Schema validation
- Response building
- Helper method organization

**Usage:**
```python
result = backend.execute_task({
    "system": "boilerplate",
    "action": "process",
    "data": "hello world"
})
```

### Example 3: Create Your Own

Start from the boilerplate and customize for your needs!

---

## Real-World Examples

### File Processing Tool

```python
class FileProcessorTool(BaseTool):
    name = "File Processor"
    description = "Process files with custom logic"

    def handle(self, schema):
        if schema.get("action") == "process":
            file_path = schema.get("file")
            with open(file_path, "r") as f:
                content = f.read()

            # Your processing logic
            result = self._process_content(content)

            return self.success(result=result)
        return self.error("Unknown action")

    def _process_content(self, content):
        # Do something with file content
        return content.upper()
```

### API Integration Tool

```python
class APIToolTool(BaseTool):
    name = "API Client"
    description = "Call external APIs"
    requires = ["requests"]

    def initialize(self) -> bool:
        ok, missing = self.validate_dependencies()
        if not ok:
            self.log(f"Missing packages: {missing}")
            return False
        return super().initialize()

    def handle(self, schema):
        if schema.get("action") == "call":
            import requests
            url = schema.get("url")
            response = requests.get(url)
            return self.success(result=response.json())
        return self.error("Unknown action")
```

### Database Tool

```python
class DatabaseTool(BaseTool):
    name = "Database"
    description = "Query and manage databases"
    requires = ["sqlite3"]

    def initialize(self) -> bool:
        self.db = None
        return super().initialize()

    def handle(self, schema):
        if schema.get("action") == "query":
            query = schema.get("query")
            results = self._execute_query(query)
            return self.success(results=results)
        return self.error("Unknown action")

    def _execute_query(self, query):
        # Execute query logic here
        pass

    def shutdown(self):
        if self.db:
            self.db.close()
```

---

## Tool Categories

### Data Processing
- Text processors
- CSV/JSON handlers
- Image processors
- Document parsers

### Code Analysis
- Linters and formatters
- Complexity analyzers
- Dependency trackers
- Type checkers

### External Integration
- API clients
- Database connectors
- Webhook handlers
- File system watchers

### Utilities
- Converters and encoders
- Math and statistics
- Cache managers
- Config managers

---

## Best Practices

### 1. Keep Tools Focused
One tool = one responsibility. Don't try to do everything in one tool.

```python
# ✓ Good
class CodeMetricsTool(BaseTool):
    name = "Code Metrics"
    # Analyzes code quality only

# ✗ Bad
class UtilityTool(BaseTool):
    name = "Utility"  # Too vague, does everything
```

### 2. Validate Input
Always validate schema before processing.

```python
def handle(self, schema):
    ok, err = self.validate_schema(schema, ["required_field"])
    if not ok:
        return self.error(err)
    # Safe to proceed
```

### 3. Handle Errors Gracefully
Catch exceptions and return proper error responses.

```python
try:
    result = risky_operation()
    return self.success(result=result)
except Exception as e:
    self.log(f"Error: {e}")
    return self.error(str(e))
```

### 4. Check Dependencies
Validate external packages are installed.

```python
def initialize(self) -> bool:
    ok, missing = self.validate_dependencies()
    if not ok:
        self.log(f"Missing: {missing}")
        return False
    return super().initialize()
```

### 5. Document Actions
Clearly document what actions your tool supports.

```python
def handle(self, schema):
    """
    Schema format:
    {
        "system": "mytool",
        "action": "analyze" | "process" | "export",
        "file": "path/to/file.py",
        "options": {...}
    }
    """
```

### 6. Log Important Events
Use `self.log()` for debugging and tracking.

```python
def _process_file(self, path):
    self.log(f"Processing: {path}")
    try:
        result = self._analyze(path)
        self.log(f"Success: found {len(result)} items")
        return result
    except Exception as e:
        self.log(f"Failed: {e}")
        raise
```

---

## Troubleshooting

### Tool Not Loading

Check the logs at boot time:

```
Auto-discovering tools...
  ✓ Loaded: Code Metrics (v1.0.0)
  ✗ Failed to load my_tool: ImportError: ...
```

**Fixes:**
- Check syntax errors in your tool file
- Ensure class inherits from `BaseTool`
- Verify all imports are available
- Check file is in `src/backend/tools/`

### "Unknown controller" Error

Tool name doesn't match. Tool key = name.lower().replace(" ", "_")

```python
name = "My New Tool"
# Accessed as "my_new_tool"

result = backend.execute_task({
    "system": "my_new_tool",  # Must match this
    "action": "..."
})
```

### Initialization Fails

Your `initialize()` method returned `False`.

```python
def initialize(self) -> bool:
    ok, missing = self.validate_dependencies()
    if not ok:
        self.log(f"Missing: {missing}")
        return False  # ← This fails loading
    return super().initialize()
```

**Fix:** Install missing packages or make them optional.

---

## Advanced: Tool Callbacks

Tools can't directly call UI functions, but they can return data that the UI acts on:

```python
# Tool returns data
result = backend.execute_task({
    "system": "mytool",
    "action": "analyze"
})

# UI receives result and responds
if result["status"] == "ok":
    # Update UI with result
    panel.update_display(result["data"])
```

---

## Next Steps

1. **Browse Examples** – Check `code_metrics_tool.py` for a realistic tool
2. **Copy Boilerplate** – Use `boilerplate_tool.py` as your starting point
3. **Implement** – Write your tool logic
4. **Test** – Call via `backend.execute_task()`
5. **Ship** – Save in `src/backend/tools/` and it's live!

---

**Version:** 1.0
**Last Updated:** 2026-03-02
