@echo off
setlocal

cd /d "%~dp0"
set "APP_URL=http://localhost:8501"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON=py -3"
    ) else (
        where python >nul 2>nul
        if not errorlevel 1 (
            set "PYTHON=python"
        ) else (
            echo Python was not found. Please install Python or create .venv first.
            pause
            exit /b 1
        )
    )
)

echo Starting BTC Quant Research Console...
echo Project: %CD%
echo URL: %APP_URL%
echo.
echo If this is the first run, install dependencies first:
echo   pip install -r requirements.txt
echo.

start "" "%APP_URL%"
%PYTHON% scripts\run_dashboard.py

if errorlevel 1 (
    echo.
    echo Dashboard exited with error code %ERRORLEVEL%.
    pause
)
