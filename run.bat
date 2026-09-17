@echo off
setlocal

rem Aerodynamic Simulation Automation Program launcher.
rem Double-click this file (or run it from a terminal) to start the app.

cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/ and make
    echo sure "Add python.exe to PATH" is checked during installation.
    pause
    exit /b 1
)

python -c "import customtkinter, numpy, pandas, matplotlib, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing/updating required Python packages...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies. See the message above.
        pause
        exit /b 1
    )
)

where wsl >nul 2>&1
if errorlevel 1 (
    echo [WARNING] WSL was not found. Simulations require WSL2 with OpenFOAM
    echo installed. See README.md for setup instructions. The GUI will still
    echo open, but "Run Simulation" will fail until WSL is set up.
)

echo Starting Aerodynamic Simulation Automation Program...
python Run.py

if errorlevel 1 (
    echo.
    echo [ERROR] The program exited with an error. See the messages above.
    pause
)

endlocal
