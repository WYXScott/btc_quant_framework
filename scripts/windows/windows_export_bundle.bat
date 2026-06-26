@echo off
setlocal
cd /d %~dp0\..\..
if not exist .venv\Scripts\python.exe (
  echo [ERROR] Virtual environment not found.
  exit /b 1
)
.venv\Scripts\python.exe scripts\export_runtime_bundle.py --include-logs
endlocal
