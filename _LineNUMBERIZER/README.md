# LineNumberizer

LineNumberizer is a tool designed to make text files and codebases "Agent-Friendly" by adding stable, parseable line numbers, or generating abstract syntax trees (AST) for Python code.

It is useful for feeding code to LLMs (Large Language Models) that need to reference specific line numbers when suggesting edits.

## Features

* **Annotate**: Add line numbers with various styles (Pipe `|`, Colon `:`, Bracket `[L#]`).
* **Strip**: Safely remove line numbers added by this tool without modifying the code content.
* **AST Export**: Generate a JSON representation of Python code structure (Tree, Flat, or Semantic blocks).
* **Line Map**: Generate a JSON map of line numbers to content hashes for integrity checking.

## How to Run

### Windows
1.  Double-click `setup_env.bat`.
2.  This will create a virtual environment, set up the project, and launch the GUI.

### Manual Run
```bash
# Run the GUI
python -m src.app

# Run the CLI directly
python src/linenumberizer.py --help