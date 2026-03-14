@echo off
REM ============================================================
REM  Graph Manifold — Diagnostic UI
REM  Activates .venv and launches the Tkinter diagnostic tool.
REM ============================================================

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found. Run setup_env.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python tools\diagnostic_ui.py %*
