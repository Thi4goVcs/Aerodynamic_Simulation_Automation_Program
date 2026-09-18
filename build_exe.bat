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
echo Packaging AeroSimApp.exe with core\Standard (needed to find the OpenFOAM
echo case templates) into a zip you can share...
if exist dist_package rmdir /s /q dist_package
mkdir dist_package\core
move AeroSimApp.exe dist_package\AeroSimApp.exe >nul
xcopy /e /i /q core\Standard dist_package\core\Standard >nul
if exist AeroSimApp-windows.zip del AeroSimApp-windows.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist_package\*' -DestinationPath 'AeroSimApp-windows.zip'"
rmdir /s /q dist_package

echo.
echo Done: AeroSimApp-windows.zip was created in this folder. Share/extract
echo THAT (not the .exe alone) -- it needs core\Standard next to it to find
echo the OpenFOAM case templates. WSL2 + OpenFOAM still need to be installed
echo separately on whichever machine runs it (see README.md).
pause
