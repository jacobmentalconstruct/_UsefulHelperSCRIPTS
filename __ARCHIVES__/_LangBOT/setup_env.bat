@echo off
setlocal

cd /d "%~dp0"
echo [INFO] Project root: %CD%

set "PY_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"

if not exist "%PY_EXE%" (
  for /f "usebackq delims=" %%I in (`py -3.12 -c "import sys; print(sys.executable)" 2^>nul`) do set "PY_EXE=%%I"
)

if not exist "%PY_EXE%" (
  echo [ERROR] Python 3.12 not found. Install 64 bit Python 3.12  python.org.
  exit /b 1
)

"%PY_EXE%" -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)"
if errorlevel 1 (
  echo [ERROR] Interpreter is not Python 3.12: %PY_EXE%
  "%PY_EXE%" -V
  exit /b 1
)

echo [INFO] Using: %PY_EXE%
"%PY_EXE%" -V

if exist ".venv" (
  echo [INFO] Removing existing .venv...
  rmdir /s /q ".venv"
)

echo [INFO] Creating .venv with Python 3.12...
"%PY_EXE%" -m venv ".venv"
if errorlevel 1 (
  echo [ERROR] venv creation failed.
  exit /b 1
)

echo [INFO] Upgrading pip tooling...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
  echo [ERROR] pip tooling upgrade failed.
  exit /b 1
)

if not exist "requirements.txt" (
  echo [ERROR] requirements.txt not found in %CD%
  exit /b 1
)

echo [INFO] Installing requirements...
".venv\Scripts\pip.exe" install -r "requirements.txt"
if errorlevel 1 (
  echo [ERROR] requirements install failed.
  exit /b 1
)

echo [INFO] pip check...
".venv\Scripts\pip.exe" check

echo [DONE] Env ready.
echo Activate with:
echo        call .venv\Scripts\activate
exit /b 0