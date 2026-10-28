@echo off
setlocal
cd /d "%~dp0"

title Abaqus-Simcenter Modal Comparator - new interface preview

set "BASE_PYTHON="
where py >nul 2>nul
if not errorlevel 1 set "BASE_PYTHON=py -3"

if not defined BASE_PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 set "BASE_PYTHON=python"
)

if not defined BASE_PYTHON (
    echo Python 3 was not found.
    echo Install Python 3 and enable the "Add Python to PATH" option.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local Python environment...
    %BASE_PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" src\ensure_dependencies.py
if errorlevel 1 goto :error

".venv\Scripts\python.exe" -c "import PySide6.QtWidgets" >nul 2>nul
if errorlevel 1 (
    echo Installing the new interface dependency PySide6 from requirements-new-gui.txt...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-new-gui.txt
    if errorlevel 1 goto :error
)

echo Starting the new interface preview...
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m new_gui
if errorlevel 1 goto :error

endlocal
exit /b 0

:error
echo.
echo The new interface could not start or finished with an error.
echo Review the messages above, then press any key.
pause >nul
endlocal
exit /b 1
