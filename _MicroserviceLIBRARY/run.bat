@echo off
setlocal

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [run] Launching Library Librarian UI
"%PYTHON_EXE%" -m library.app_factory launch-ui
exit /b %errorlevel%
