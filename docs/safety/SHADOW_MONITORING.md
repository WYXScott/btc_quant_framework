# V2.1 Shadow Monitoring

V2.1 adds a read-only shadow-live vs local paper/ensemble monitoring layer. It is designed to answer one operational question before any live automation is considered:

> Does the live read-only account state match the strategy target and the local paper state closely enough to trust the system state?

This version does **not** submit live orders.

## What it compares

The monitor compares four sources:

1. `shadow_live_snapshots` — read-only live or offline preview account snapshot.
2. `account_state` / `equity_curve` — local SQLite paper account state.
3. `target_exposure_decisions` — latest ensemble target exposure decision.
4. `LiveSafetyGate` — live master switch, kill switch, hard circuit, unknown order checks.

## Main scripts

Create a shadow drift report:

```bash
python scripts/shadow_drift_check.py
```

Use real read-only live private endpoints, only if you created read-only API keys:

```bash
set BINANCE_LIVE_READONLY_API_KEY=your_readonly_key
set BINANCE_LIVE_READONLY_API_SECRET=your_readonly_secret
python scripts/shadow_drift_check.py --fetch-live-readonly
```

Run a finite monitor loop:

```bash
python scripts/shadow_monitor_loop.py --max-iterations 3 --interval-seconds 300
```

Build the V2.1 readiness report:

```bash
python scripts/v21_shadow_readiness_report.py
```

Export monitor tables:

```bash
python scripts/shadow_monitor_export.py
```

## Outputs

Default output directory:

```text
reports/shadow_monitor/
```

Key files:

```text
shadow_drift_report.json
shadow_drift_checks.csv
shadow_monitor_summary.csv
shadow_monitor_panel.html
v2_1_shadow_readiness_report.json
```

## Status logic

- `blocked`: missing paper state or missing shadow snapshot when no fallback is allowed.
- `warn`: equity drift, position drift, stale state, missing target exposure, or target exposure mismatch.
- `pass`: no blockers and no warnings.

A blocked `LiveSafetyGate` is **expected** while the framework is in demo/shadow mode. It is displayed in the panel but does not itself make the V2.1 drift report fail.

## Important safety rule

Never use trading-enabled API keys for shadow-live checks. The shadow client is designed for read-only calls, but API permission should also be restricted at the exchange level.
