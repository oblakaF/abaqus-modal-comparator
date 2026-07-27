@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="

where python >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    echo Python was not found.
    echo Install Python 3 and enable the "Add Python to PATH" option.
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import PIL" >nul 2>nul
if errorlevel 1 (
    echo Installing the image-preview dependency...
    %PYTHON_CMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo The required package could not be installed.
        echo Run this command manually:
        echo %PYTHON_CMD% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo Starting Abaqus Modal Comparator...
%PYTHON_CMD% src\main.py

if errorlevel 1 (
    echo.
    echo The program finished with an error.
    pause
)

endlocal
