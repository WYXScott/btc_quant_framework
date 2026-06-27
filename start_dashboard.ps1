$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "Missing .venv. Create and install dependencies first:" -ForegroundColor Yellow
    Write-Host "  py -3 -m venv .venv"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  python -m pip install --upgrade pip setuptools wheel"
    Write-Host "  python -m pip install -r requirements.txt"
    exit 1
}

Write-Host "Starting BTC Quant Research Console..."
Write-Host "Project: $(Get-Location)"
Write-Host "Python: $(python -c 'import sys; print(sys.executable)')"
Write-Host "URL: http://localhost:8501"
python scripts\run_dashboard.py --open-browser
