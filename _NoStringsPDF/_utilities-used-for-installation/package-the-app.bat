@echo off
:: [FIX 1] Switch to Project Root so we can find src/ and assets/
pushd "%~dp0.."

set "APP_NAME=NoStringsPDF"

echo ---------------------------------------------------------------------
echo [BUILD SYSTEM] Starting Release Build for %APP_NAME%...
echo ---------------------------------------------------------------------

:: 1. ACTIVATE ENVIRONMENT
if exist .venv\Scripts\activate (
    call .venv\Scripts\activate
) else (
    echo [ERROR] Virtual environment not found. Run setup_env.bat first.
    pause
    exit /b
)

:: [FIX 2] AUTO-INSTALL PYINSTALLER if missing
:: We check if the command exists. If not, we pip install it locally.
where pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo [SYSTEM] PyInstaller not found in venv. Installing...
    pip install pyinstaller
)

:: 2. CLEANUP PREVIOUS BUILDS
echo.
echo [CLEAN] Removing old build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist *.spec del /q *.spec
if exist "%APP_NAME%_Release.zip" del /q "%APP_NAME%_Release.zip"

:: 3. BUILD EXECUTABLE
echo.
echo [COMPILE] Generating EXE...
:: --paths: WE ADD "src;src/microservices" so it finds the missing library!

pyinstaller --noconsole --onefile ^
    --name "%APP_NAME%" ^
    --icon="app.ico" ^
    --paths="src;src/microservices" ^
    --hidden-import="microservice_std_lib" ^
    --hidden-import="PIL" ^
    --hidden-import="fitz" ^
    --hidden-import="pymupdf" ^
    src/app.py

:: 4. STAGE ASSETS
echo.
echo [STAGE] Copying assets to distribution folder...
if exist assets (
    xcopy /E /I /Y "assets" "dist\assets"
) else (
    echo [WARNING] No assets folder found! Icons will be missing.
)

:: 5. PACKAGE
echo.
echo [PACKAGE] Zipping distribution into single file...
powershell Compress-Archive -Path "dist\*" -DestinationPath "%APP_NAME%_Release.zip" -Force

echo.
echo ---------------------------------------------------------------------
echo [SUCCESS] BUILD COMPLETE!
echo ---------------------------------------------------------------------
echo.
echo You have two options:
echo 1. The Folder:  dist\ (In project root)
echo 2. The Zip:     %APP_NAME%_Release.zip  (SEND THIS ONE)
echo.
pause
popd