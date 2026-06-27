# Pre-commit check script for BTC Quant Framework
# Run before each commit to validate code quality locally.
#
# Install: copy or symlink to .git/hooks/pre-commit
#   Copy-Item scripts/pre-commit-check.ps1 .git/hooks/pre-commit
#
# Or use the pre-commit framework:
#   pip install pre-commit
#   pre-commit install

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "[pre-commit] Running smoke test..." -ForegroundColor Cyan
python tests/smoke_test.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[pre-commit] Smoke test FAILED — commit aborted." -ForegroundColor Red
    exit 1
}

Write-Host "[pre-commit] All checks passed." -ForegroundColor Green
