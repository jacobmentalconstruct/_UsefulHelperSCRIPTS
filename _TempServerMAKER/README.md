🖥️ T E M P S E R V E R M A K E R ══════════════════════════════

TempServerMAKER is a simple, standalone tool that serves a local project directory as an interactive web page. It's designed for securely feeding your project's source code to Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG) systems.

It runs as a portable Python application with a graphical user interface to manage the server, making it easy to run on Windows, macOS, and Linux without external dependencies.

✨ FEATURES ══════════════════════════════

    Desktop GUI Control: A simple Tkinter-based GUI to easily select the project folder, set the port, and start/stop/restart the server.

    Interactive Web UI: Serves a clean, modern web interface with a collapsible file tree, tabbed file viewer, and in-browser AST (Abstract Syntax Tree) generation for Python files.

    Advanced Exporting: Export the entire project from the web UI in multiple formats:

        AI Report (.txt): A single, comprehensive text file with all file contents.

        Project Codebase Log (JSONL): A detailed machine-readable log of all files.

        AST Tree Log (JSONL): A complete AST dump for all Python files.

    Client-Server Architecture: Separates the Python backend (app.py) from the frontend (HTML, CSS, JS), making the code easy to maintain and customize.

    No Installation Needed: Runs on any system with a standard Python 3 (with Tkinter) installation.

⚙️ HOW TO USE ══════════════════════════════

► On Windows ────────────────────────────

    Place the _Temp-Server-Maker/ folder (containing the start_app.py script) inside your project directory.

    Open the _Temp-Server-Maker/ folder and double-click the start_app.py file to start the server.

    The desktop GUI will open. Click "Start" and your web browser will launch automatically.

    When you are finished, click "Quit" in the GUI or close the terminal window.

► On macOS or Linux (Ubuntu, etc.) ──────────────────────────── First-Time Setup (One Time Only): Before running the script for the first time, you need to make it executable.

    Open your Terminal application.

    Navigate into the _Temp-Server-Maker/ folder.

    Run the following command and press Enter:
    Bash

    chmod +x start_app.py

Running the Application:

    Open a terminal in the _Temp-Server-Maker/ folder.

    Run the application by typing:
    Bash

    ./start_app.py

    The desktop GUI will open. Click "Start" and your web browser will launch automatically.

    To stop the server, click "Quit" in the GUI or go back to the terminal and press Ctrl+C.

💡 HOW IT WORKS ══════════════════════════════ This application is built with Python's standard http.server and tkinter libraries. It operates on a client-server model:

    Back-End (_src/app.py): A Python script that runs the Tkinter GUI and acts as a web server. When started, it scans the project directory, serves the frontend files, and provides a simple API for project data and exports.

    Front-End (_src/index.html, _src/style.css, _src/index.js): A modern, single-page web application that runs in your browser. It fetches the file data from the Python backend and dynamically renders the interactive UI.