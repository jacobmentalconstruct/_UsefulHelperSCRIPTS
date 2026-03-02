@echo off
setlocal
echo [SYSTEM] Performing Nuclear Reset and Environment Initialization...

:: 0. Clean up old environments and caches
echo [SYSTEM] Purging old .venv, venv, and __pycache__...
if exist .venv rd /s /q .venv 
if exist venv rd /s /q venv
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
del /s /q *.pyc >nul 2>&1

:: 1. Create the venv
echo [SYSTEM] Creating fresh .venv...
py -m venv .venv 

:: 2. Upgrade pip and install requirements
echo [SYSTEM] Installing dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip 
if exist requirements.txt (
    .venv\Scripts\pip install -r requirements.txt 
) else (
    echo [WARNING] requirements.txt not found!
)

echo.
echo [SUCCESS] Environment is now clean and ready! 
echo To launch the Workbench, run: .venv\Scripts\python.exe -m src.app 
pause