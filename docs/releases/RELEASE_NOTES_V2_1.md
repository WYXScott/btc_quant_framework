# BTC Quant Framework V2.1 Release Notes

## Theme

Read-only shadow-live vs local paper/ensemble divergence monitoring.

## Added

- `crypto_quant.live.shadow_monitor`
- SQLite tables:
  - `shadow_monitor_reports`
  - `shadow_monitor_checks`
- Scripts:
  - `scripts/shadow_drift_check.py`
  - `scripts/shadow_monitor_loop.py`
  - `scripts/shadow_monitor_export.py`
  - `scripts/v21_shadow_readiness_report.py`
- HTML dashboard:
  - `reports/shadow_monitor/shadow_monitor_panel.html`
- Documentation:
  - `docs/SHADOW_MONITORING.md`

## Safety boundary

V2.1 does not enable live order execution. It only compares read-only live snapshots, local paper account state, and ensemble target exposure decisions.
