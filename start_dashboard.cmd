@echo off
setlocal

cd /d "%~dp0"
set "APP_URL=http://localhost:8501"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo Missing .venv. Create and install dependencies first:
    echo   py -3 -m venv .venv
    echo   call .venv\Scripts\activate.bat
    echo   python -m pip install --upgrade pip setuptools wheel
    echo   python -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting BTC Quant Research Console...
echo Project: %CD%
echo URL: %APP_URL%
echo Python:
python -c "import sys; print(sys.executable)"
echo.

python scripts\run_dashboard.py --open-browser
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
    echo.
    echo Dashboard exited with error code %EXITCODE%.
    echo If PowerShell blocked start_dashboard.ps1, run this file instead:
    echo   .\start_dashboard.cmd
    pause
)
exit /b %EXITCODE%
