@echo off
REM ============================================================
REM  Graph Manifold — Environment Setup
REM  Creates an isolated .venv and installs the project into it.
REM  Run this once, or again after pulling major changes.
REM ============================================================

echo.
echo === Graph Manifold Environment Setup ===
echo.

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    echo Install Python 3.11+ and ensure it is on your PATH.
    pause
    exit /b 1
)

REM Create .venv if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created at .venv\
) else (
    echo Virtual environment already exists at .venv\
)

REM Activate and install
echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip --quiet

echo Installing project in editable mode...
pip install -e . --quiet

echo Installing test dependencies...
pip install pytest --quiet

echo.
echo === Setup Complete ===
echo.
echo   To activate manually:  .venv\Scripts\activate
echo   To run the app:        run.bat
echo   To run tests:          test.bat
echo   To deactivate:         deactivate
echo.
pause
