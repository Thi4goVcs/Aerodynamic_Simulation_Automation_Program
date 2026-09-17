@echo off
REM Builds a standalone AeroSimApp.exe next to this script (and next to
REM core/), so it can find functions.py and the OpenFOAM case templates.
python -m pip install --quiet pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller. Is Python/pip on PATH?
    pause
    exit /b 1
)

python -m PyInstaller --onefile --windowed --name AeroSimApp --collect-all customtkinter --paths core --distpath . --noconfirm Run.py
if errorlevel 1 (
    echo Build failed -- see the PyInstaller output above.
    pause
    exit /b 1
)

echo.
echo Done: AeroSimApp.exe was created in this folder.
echo Keep it here, next to core/, Results/, etc. -- it looks for them
echo relative to its own location, not the folder you launch it from.
pause
