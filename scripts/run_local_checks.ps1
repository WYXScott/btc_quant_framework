$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
    Write-Host "Missing project virtual environment: .venv" -ForegroundColor Red
    Write-Host "Create it first:" 
    Write-Host "  py -3 -m venv .venv"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  python -m pip install --upgrade pip setuptools wheel"
    Write-Host "  python -m pip install -r requirements.txt"
    exit 1
}

. .\.venv\Scripts\Activate.ps1

Write-Host "[1/4] Runtime environment check"
python scripts\check_runtime_env.py --strict

Write-Host "[2/4] Stability check"
python scripts\run_stability_check.py

Write-Host "[3/4] Managed service status"
python scripts\manage_services.py status

Write-Host "[4/4] Smoke test"
python tests\smoke_test.py

Write-Host "Local checks completed successfully."
