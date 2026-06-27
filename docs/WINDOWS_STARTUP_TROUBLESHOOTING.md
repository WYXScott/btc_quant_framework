# Windows Startup Troubleshooting

This page documents the preferred Windows launch path for the Streamlit dashboard.

## Preferred launcher from PowerShell

PowerShell can block unsigned `.ps1` scripts depending on local or enterprise
execution policy. Use the `.cmd` launcher from the repository root because it is
not subject to PowerShell script-signing policy:

```powershell
.\start_dashboard.cmd
```

The `.cmd` launcher activates the project `.venv`, prints the Python executable,
and starts Streamlit through:

```powershell
python scripts\run_dashboard.py --open-browser
```

## Manual fallback

If a launcher fails, activate `.venv` first and start the dashboard directly:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\run_dashboard.py --open-browser
```

If PowerShell blocks `Activate.ps1`, use Command Prompt activation instead:

```bat
call .venv\Scripts\activate.bat
python scripts\run_dashboard.py --open-browser
```

## Diagnose startup prerequisites

Run:

```powershell
python scripts\diagnose_dashboard_startup.py
```

The diagnostic script writes:

```text
reports/runtime/dashboard_startup_diagnostics.json
```

It checks the active Python interpreter, project `.venv`, Streamlit importability,
port availability, launcher file presence, and PowerShell execution policy when
running on Windows.

## PowerShell bypass command

For one-off local use, the `.ps1` launcher can be run with a process-scoped
execution-policy bypass:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_dashboard.ps1
```

Do not change machine-wide execution policy just to run this project. Prefer
`.\start_dashboard.cmd`.
