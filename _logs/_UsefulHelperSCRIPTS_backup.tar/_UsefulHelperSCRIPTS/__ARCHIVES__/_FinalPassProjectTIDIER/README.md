# 🧹 Project Tidier (FinalPass)

**Project Tidier** is an automated source code refinement tool within the **_UsefulHelperSCRIPTS** ecosystem. It serves as a final "sanity check" before pushing local code to public repositories like GitHub. By leveraging local AI models (via Ollama) and a suite of specialized microservices, it identifies and removes internal development clutter, LLM-generated chatter, and inconsistent formatting.

## 🚀 Key Features

* 
**AI-Driven Scrubbing**: Uses local **Qwen 2.5** (1.5b or 3b) models to detect and strip out "LLM fingerprints" and internal scratch-pad comments.


* 
**Semantic Hunking**: Slices Python files into logical units (Classes and Functions) using AST parsing to ensure the AI has complete context for every change.


* 
**Side-by-Side Review**: A dual-pane Tkinter interface powered by the `DiffEngineMS` allows you to manually approve or skip every proposed deletion.


* 
**Structural Linting**: Automatically fixes "staircase" indentation and whitespace issues after the AI pass using the **Architect** engine.


* 
**Privacy Guard**: Performs a final pass to ensure internal naming conventions are standardized to public-facing formats.



## 🏗️ Technical Architecture

This project follows a decoupled **Triad Pattern** to separate the user interface from the heavy-lifting logic.

* **The Ignition (`app.py`)**: A "dumb" entry point that initializes the shared **Signal Bus** and bridges the two main pillars.
* **The Brain (`backend.py`)**: An orchestrator that manages the flow of data between the file scanner, the semantic chunker, and the local AI instance.
* **The Face (`ui.py`)**: A dark-themed Tkinter dashboard that hosts the file explorer, telemetry logs, and the review stage.

## 🛠️ Installation & Setup

1. 
**Initialize Environment**: Run the provided batch script to set up your local virtual environment.


```bash
setup_env.bat

```


2. 
**Ollama Connection**: Ensure you have [Ollama](https://ollama.com/) running locally with the `qwen2.5:1.5b` or `qwen2.5:3b` models pulled.


3. **Launch**:
```bash
.venv\Scripts\python.exe app.py

```



---

## 🧩 Orchestrated Microservices

This app utilizes the following components from the `src/microservices` library:

* 
**`_SemanticChunkerMS`**: The Surgeon — Logical code splitting.


* 
**`_DiffEngineMS`**: The Timekeeper — Hybrid versioning and delta tracking.


* 
**`_CodeFormatterMS`**: The Architect — Structural normalization.


* 
**`_ExplorerWidgetMS`**: The Navigator — Visual directory selection.


* **`_SignalBusMS`**: The Spine — Decoupled event-driven communication.
