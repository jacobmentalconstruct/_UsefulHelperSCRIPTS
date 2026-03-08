@echo off
setlocal
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"
call run_sandboxer.bat %*
exit /b %errorlevel%
