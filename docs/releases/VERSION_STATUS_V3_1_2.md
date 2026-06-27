# V3.1.2 Version Status And Windows Startup Reliability

V3.1.2 is a local-runtime hardening release focused on Windows dashboard startup.

## What changed

- Added `start_dashboard.cmd` as the preferred PowerShell-safe launcher.
- Kept `start_dashboard.bat` as a compatibility wrapper around the `.cmd` launcher.
- Updated `scripts/run_dashboard.py` with explicit CLI options, Streamlit import checks, browser opening, UTF-8 environment defaults, and clearer diagnostics.
- Added `scripts/diagnose_dashboard_startup.py` for local startup diagnostics.
- Added `docs/WINDOWS_STARTUP_TROUBLESHOOTING.md`.
- Updated documentation to recommend `.\start_dashboard.cmd` when running from PowerShell.

## Stability status

The V3.1.1 user-side checks showed:

- `scripts/check_runtime_env.py --strict`: pass
- `scripts/run_stability_check.py`: pass
- `scripts/manage_services.py status`: pass
- `tests/smoke_test.py`: pass
- `start_dashboard.ps1`: blocked by local PowerShell script execution policy

V3.1.2 addresses that final startup issue without requiring global execution-policy changes.

## Recommended launch command

From repository root in PowerShell:

```powershell
.\start_dashboard.cmd
```

Manual fallback:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\run_dashboard.py --open-browser
```

If PowerShell blocks activation scripts, use Command Prompt:

```bat
call .venv\Scripts\activate.bat
python scripts\run_dashboard.py --open-browser
```
