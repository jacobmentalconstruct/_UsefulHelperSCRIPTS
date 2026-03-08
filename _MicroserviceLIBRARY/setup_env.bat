@echo off
setlocal

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

where python >nul 2>nul
if errorlevel 1 (
    echo [setup_env] Python was not found on PATH.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [setup_env] Creating virtual environment in .venv
    python -m venv .venv
    if errorlevel 1 exit /b 1
) else (
    echo [setup_env] Reusing existing .venv
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1

echo [setup_env] Upgrading pip
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1

if exist "requirements.txt" (
    echo [setup_env] Installing requirements from requirements.txt
    python -m pip install -r requirements.txt
    if errorlevel 1 exit /b 1
)

echo [setup_env] Environment ready.
echo [setup_env] Launch with run.bat
exit /b 0
