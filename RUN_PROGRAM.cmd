@echo off
cd /d "%~dp0"

python src\main.py

if errorlevel 1 (
    echo.
    echo Program finished with an error.
    pause
)