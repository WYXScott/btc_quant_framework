# Release Notes V3.1.1

V3.1.1 focuses on local runtime reliability. It makes virtual-environment usage
explicit and reduces the risk of launching services with the wrong Python
interpreter.

## Added

- `scripts/check_runtime_env.py` for project-local `.venv`, Python version,
  dependency, and runtime path checks.
- `scripts/run_local_checks.bat` and `scripts/run_local_checks.ps1` to activate
  `.venv` before running runtime, stability, service-status, and smoke checks.
- `start_dashboard.ps1` as a PowerShell dashboard launcher.
- `docs/LOCAL_ENVIRONMENT.md` with Windows-first venv setup and operating steps.
- `src/crypto_quant/utils/runtime_env.py` for reusable virtual-environment and
  project Python resolution helpers.

## Changed

- Project version updated to `3.1.1`.
- `start_dashboard.bat` now requires and activates `.venv` before starting
  Streamlit.
- Managed services now prefer the project `.venv` Python executable when
  launched from the WebUI or `scripts/manage_services.py`.
- Service status now exposes `python_executable` so operators can verify which
  interpreter will run background services.
- Stability check now includes local runtime environment and venv-related checks.

## Safety note

This release does not enable live trading. Default execution remains local paper
trading, and live/demo order submission remains blocked by the existing safety
configuration.
