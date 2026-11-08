@echo off
setlocal
cd /d "%~dp0"

rem Main launcher. Default: the PySide6 program, through RUN_NEW_GUI.cmd (its own environment and dependency setup).
rem "RUN_PROGRAM.cmd legacy" starts the legacy interface (src\main.py) with the setup below.

if /i "%~1"=="legacy" goto :legacy
if not "%~1"=="" (
    echo Unknown option "%~1". Use RUN_PROGRAM.cmd for the program, or RUN_PROGRAM.cmd legacy for the legacy interface.
    endlocal
    exit /b 2
)

call "%~dp0RUN_NEW_GUI.cmd"
set "RESULT=%errorlevel%"
endlocal & exit /b %RESULT%

:legacy
title Abaqus-Simcenter Modal Comparator (legacy interface)

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

echo Starting Abaqus-Simcenter Modal Comparator (legacy interface)...
".venv\Scripts\python.exe" src\main.py
if errorlevel 1 goto :error

endlocal
exit /b 0

:error
echo.
echo The program could not start or finished with an error.
echo Review the messages above, then press any key.
pause >nul
endlocal
exit /b 1
