@echo off
setlocal

echo [STATUS] Searching for Python 3.10...
py -3.10 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.10 was not found. Please install it from python.org.
    pause
    exit /b
)

echo [STATUS] Setting up The DISMANTLER environment with Python 3.10...
if not exist .venv (
    py -3.10 -m venv .venv
)

call .venv\Scripts\activate

echo [STATUS] Installing dependencies from requirements.txt...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo [STATUS] Setup Complete.
echo ----------------------------------------------------------------------
echo  Starting The DISMANTLER v2.1...
echo ----------------------------------------------------------------------
python -m src.app
pause
