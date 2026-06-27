@echo off
setlocal
cd /d "%~dp0\.."

if not exist ".venv\Scripts\activate.bat" (
    echo Missing project virtual environment: .venv
    echo Create it first:
    echo   py -3 -m venv .venv
    echo   call .venv\Scripts\activate.bat
    echo   python -m pip install --upgrade pip setuptools wheel
    echo   python -m pip install -r requirements.txt
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo [1/4] Runtime environment check
python scripts\check_runtime_env.py --strict || exit /b 1

echo [2/4] Stability check
python scripts\run_stability_check.py || exit /b 1

echo [3/4] Managed service status
python scripts\manage_services.py status || exit /b 1

echo [4/4] Smoke test
python tests\smoke_test.py || exit /b 1

echo Local checks completed successfully.
