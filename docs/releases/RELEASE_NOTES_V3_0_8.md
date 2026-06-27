# BTC Quant Framework V3.0.8

V3.0.8 is a stability-closure release. It does not open new trading capabilities; it adds an offline release-readiness check and makes the current system state easier to audit from the WebUI.

## Added

- `scripts/run_stability_check.py` for offline release-readiness checks.
- Stability report outputs:
  - `reports/stability/stability_report.json`
  - `reports/stability/stability_checks.csv`
- Streamlit **软件审查** stability summary and run button.
- Streamlit **流程中心** stability-check step.
- Current-version status and next-development recommendation document:
  - `docs/VERSION_STATUS_V3_0_8.md`

## Checks Covered

- Required repository files and current release notes.
- UI safe-mode script whitelist integrity.
- Live-trading safety switches.
- Runtime artifact presence.
- Realtime SQLite schema if the realtime database exists.
- README and version-document consistency.

## Safety

- The stability check is local and offline.
- No live-trading controls are added.
- Missing runtime data/model artifacts are warnings unless they indicate a broken release surface.
