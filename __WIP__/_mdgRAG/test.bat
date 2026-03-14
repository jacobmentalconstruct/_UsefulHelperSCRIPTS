@echo off
REM ============================================================
REM  Graph Manifold — Run Tests
REM  Activates .venv and runs pytest.
REM ============================================================

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found. Run setup_env.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m pytest tests/ -v %*
