@echo off
REM ============================================================
REM  Graph Manifold — Web UI Launcher
REM  Activates .venv and starts the interactive web UI.
REM  Usage:  run.bat                      (opens UI, no DB pre-loaded)
REM          run.bat myproject.db          (opens UI with DB pre-loaded)
REM          run.bat myproject.db 9090     (custom port)
REM ============================================================

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found. Run setup_env.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

set DB_ARG=
set PORT=8080

if not "%~1"=="" set DB_ARG=--db "%~1"
if not "%~2"=="" set PORT=%~2

echo.
echo  Graph Manifold UI starting on http://localhost:%PORT%
echo  Press Ctrl+C to stop.
echo.

python -m src.app serve %DB_ARG% --port %PORT%
