# Version Status V3.1.1

## Status

V3.1.1 is a local-runtime hardening release on top of V3.1.0. It keeps the
managed service console and previous safety hardening, then adds explicit virtual
environment handling.

## Main objective

Reduce local run failures caused by using the wrong Python interpreter.

## Completed

- Added strict runtime environment checker: `scripts/check_runtime_env.py`.
- Added local verification wrappers that activate `.venv` first:
  - `scripts/run_local_checks.bat`
  - `scripts/run_local_checks.ps1`
- Added PowerShell dashboard launcher: `start_dashboard.ps1`.
- Updated `start_dashboard.bat` to require and activate `.venv`.
- Added reusable runtime helper module:
  - `src/crypto_quant/utils/runtime_env.py`
- Updated managed-service launching so services prefer `.venv` Python.
- Extended stability checks with runtime and project-venv status.
- Added local environment operating guide:
  - `docs/LOCAL_ENVIRONMENT.md`

## Expected local command sequence

PowerShell:

```powershell
cd C:\path\to\btc_quant_framework
.\.venv\Scripts\Activate.ps1
python scripts\check_runtime_env.py --strict
python scripts\run_stability_check.py
python scripts\manage_services.py status
python tests\smoke_test.py
```

Command Prompt:

```bat
cd C:\path\to\btc_quant_framework
call .venv\Scripts\activate.bat
python scripts\check_runtime_env.py --strict
python scripts\run_stability_check.py
python scripts\manage_services.py status
python tests\smoke_test.py
```

## Remaining limitations

- OKX private order execution is still intentionally not implemented.
- Backtest and paper trading are still approximate simulations, not exchange-grade
  matching or margin engines.
- Missing local data, SQLite databases, models, and generated reports are normal
  in a clean source checkout.
