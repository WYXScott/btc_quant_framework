# Release Notes V3.1.2

## Windows dashboard startup hardening

V3.1.2 makes the local dashboard easier to start on Windows machines where
PowerShell blocks unsigned `.ps1` scripts.

### Added

- `start_dashboard.cmd`: preferred launcher from PowerShell or Command Prompt.
- `scripts/diagnose_dashboard_startup.py`: local dashboard startup diagnostics.
- `docs/WINDOWS_STARTUP_TROUBLESHOOTING.md`: troubleshooting guide for execution policy, `.venv`, Streamlit, and port checks.
- `docs/VERSION_STATUS_V3_1_2.md`: current version status.

### Changed

- `start_dashboard.bat` now delegates to `start_dashboard.cmd`.
- `scripts/run_dashboard.py` now supports `--host`, `--port`, `--open-browser`, `--no-browser`, and explicit Streamlit dependency checks.
- README and local environment docs now recommend `.\start_dashboard.cmd` as the safe Windows launcher.
- Stability checks now include the `.cmd` launcher, dashboard diagnostic script, and Windows startup troubleshooting document.

### Why

A user-side V3.1.1 validation run passed runtime checks, stability checks, service status, and smoke tests, but `start_dashboard.ps1` was blocked by PowerShell execution policy because the script was unsigned. V3.1.2 avoids requiring global policy changes by making the `.cmd` launcher the primary Windows path.
