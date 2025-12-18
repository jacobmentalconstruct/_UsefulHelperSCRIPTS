@echo off
setlocal enabledelayedexpansion

:: Set the script to work in the directory where it is located
cd /d "%~dp0"

echo ========================================================
echo      MICROSERVICE CANONICAL NAMING UTILITY
echo ========================================================
echo.

for /d %%D in (*) do (
    set "folder=%%D"
    
    :: Skip special folders if any
    if not "!folder!"=="_logs" (
        pushd "!folder!"
        
        :: Count .py files in this folder
        set count=0
        for %%f in (*.py) do set /a count+=1
        
        if !count! EQU 1 (
            :: EXACTLY ONE FILE: Safe to rename
            for %%f in (*.py) do (
                if /i "%%f" neq "app.py" (
                    echo [RENAME] !folder!\%%f -^> app.py
                    ren "%%f" "app.py"
                ) else (
                    echo [OK]     !folder! is already canonical.
                )
            )
        ) else (
            :: MULTIPLE FILES: Unsafe, user must handle
            echo [SKIP]   !folder! has !count! Python files. Manual check required.
        )
        
        popd
    )
)

echo.
echo ========================================================
echo  RECOMMENDED MANUAL ACTIONS:
echo  1. Go to _GraphEngine/
echo  2. Rename 'app.py' (Physics) -^> 'graph_engine.py'
echo  3. Rename 'graph_view.py' (Service) -^> 'app.py'
echo ========================================================
pause