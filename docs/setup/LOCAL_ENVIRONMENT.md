# Local Python Environment

This project should be run from the repository-local virtual environment `.venv`.
Do not rely on a global Python interpreter for dashboard, service, model-training,
or paper-trading commands.

## First-time Windows setup

PowerShell:

```powershell
cd C:\path\to\btc_quant_framework
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Command Prompt:

```bat
cd C:\path\to\btc_quant_framework
py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

## Every local run

Activate the environment first.

PowerShell:

```powershell
cd C:\path\to\btc_quant_framework
.\.venv\Scripts\Activate.ps1
```

Command Prompt:

```bat
cd C:\path\to\btc_quant_framework
call .venv\Scripts\activate.bat
```

Then run project commands with `python`, for example:

```powershell
python scripts\check_runtime_env.py --strict
python scripts\run_stability_check.py
python scripts\manage_services.py status
```

## One-command local verification

PowerShell:

```powershell
.\scripts\run_local_checks.ps1
```

Command Prompt:

```bat
scripts\run_local_checks.bat
```

The wrapper scripts activate `.venv` before running the runtime environment check,
stability check, managed-service status command, and smoke test.

## Dashboard startup

Use the `.cmd` launcher from the repository root. It works from both PowerShell and Command Prompt and avoids PowerShell unsigned-script execution-policy problems:

```powershell
.\start_dashboard.cmd
```

Command Prompt:

```bat
start_dashboard.cmd
```

`start_dashboard.bat` remains as a compatibility wrapper around `start_dashboard.cmd`. The `.ps1` launcher is still available, but some Windows systems block unsigned `.ps1` scripts.

Manual fallback after activation:

```powershell
python scripts\run_dashboard.py --open-browser
```

Startup diagnostics:

```powershell
python scripts\diagnose_dashboard_startup.py
```

See [Windows Startup Troubleshooting](WINDOWS_STARTUP_TROUBLESHOOTING.md).

## Managed service launcher behavior

V3.1.1 makes the service manager prefer the project `.venv` Python executable
when starting background services. This prevents long-running services from being
started with a global Python interpreter by accident.

The service status output now includes the Python executable that will be used:

```powershell
python scripts\manage_services.py status
```

Look for `python_executable` in the JSON output.

## Troubleshooting

If a command reports missing packages even after installation, recreate `.venv`:

```powershell
if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python scripts\check_runtime_env.py --strict
```

Use `python -m pip ...` rather than plain `pip ...` so the installer is bound to
the active virtual environment.
