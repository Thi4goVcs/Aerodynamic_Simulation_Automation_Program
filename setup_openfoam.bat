@echo off
setlocal

rem One-time setup helper for WSL2 + OpenFOAM v2212. Run this from a normal
rem (non-administrator) terminal; it asks for elevation only for the WSL
rem install step, if that's still needed.

where wsl >nul 2>&1
if errorlevel 1 (
    echo [1/2] WSL was not found. Installing WSL2 + Ubuntu-22.04...
    echo This step needs Administrator rights and may ask you to restart Windows.
    powershell -NoProfile -Command "Start-Process wsl -ArgumentList '--install -d Ubuntu-22.04' -Verb RunAs -Wait"
    echo.
    echo WSL install was launched. If Windows asks you to restart, do that now,
    echo then finish the Ubuntu first-run setup ^(it will open and ask you to
    echo create a username/password -- that part can't be automated^), and
    echo run this script again to install OpenFOAM.
    pause
    exit /b 0
)

echo [1/2] WSL already installed, checking for OpenFOAM...
wsl -e bash -c "source /usr/lib/openfoam/openfoam2212/etc/bashrc 2>/dev/null; command -v blockMesh" >nul 2>&1
if not errorlevel 1 (
    echo OpenFOAM v2212 is already installed and working. Nothing to do.
    pause
    exit /b 0
)

echo [2/2] Installing OpenFOAM v2212 inside WSL...
echo This runs "sudo apt-get install", so it will ask for your WSL/Ubuntu
echo password interactively.
wsl -e bash -c "sudo sh -c 'wget -O - https://dl.openfoam.org/gpg.key | apt-key add -' && sudo add-apt-repository -y http://dl.openfoam.org/ubuntu && sudo apt-get update && sudo apt-get install -y openfoam2212-default && (grep -q 'openfoam2212/etc/bashrc' ~/.bashrc || echo 'source /opt/openfoam2212/etc/bashrc' >> ~/.bashrc)"
if errorlevel 1 (
    echo.
    echo [ERROR] OpenFOAM install failed -- see the messages above. You can
    echo also follow the manual steps in README.md instead.
    pause
    exit /b 1
)

echo.
echo Verifying...
wsl -e bash -c "source /usr/lib/openfoam/openfoam2212/etc/bashrc 2>/dev/null; blockMesh -help" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Could not confirm blockMesh is on PATH. Check README.md's
    echo troubleshooting section.
) else (
    echo Done: OpenFOAM v2212 is installed and working.
)
pause
