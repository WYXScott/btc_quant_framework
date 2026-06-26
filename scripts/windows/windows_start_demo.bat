@echo off
setlocal
cd /d %~dp0\..\..
if not exist .venv\Scripts\python.exe (
  echo [ERROR] Virtual environment not found. Run: python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -r requirements.txt
  exit /b 1
)
.venv\Scripts\python.exe scripts\deploy_check.py
if errorlevel 1 (
  echo [ERROR] Deployment check failed. Fix the reported issues before starting the demo service.
  exit /b 1
)
.venv\Scripts\python.exe scripts\run_demo_service.py --max-iterations 1
endlocal
