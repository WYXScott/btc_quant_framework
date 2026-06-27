# V3.0 Operations Daily Reports

V3.0 adds a research-only operations layer for long-running BTC paper/demo validation. It does **not** enable live trading.

## What it monitors

- Paper-trading equity, drawdown, realized PnL, latest position and target exposure.
- Recent orders and target-exposure decisions.
- Unified model/strategy admission leaderboard and admission changes over time.
- Walk-forward calibrated probability drift.
- Rolling signal hit-rate and hit-rate by confidence tier.
- Strategy failure status when available.
- Live gate, shadow-monitor and data-quality report status.

## Main commands

```bash
python scripts/run_paper_health_check.py
python scripts/run_signal_hit_rate_report.py
python scripts/run_daily_operations_report.py
python scripts/build_v30_operations_report.py
```

## Main outputs

```text
reports/operations/daily_operations_report.html
reports/operations/daily_operations_summary.json
reports/operations/daily_operations_alerts.csv
reports/operations/daily_admission_leaderboard_top.csv
reports/operations/daily_signal_hit_rate_by_tier.csv
reports/v3_0_operations_report/v3_0_operations_report.html
```

## Frontend

Run:

```bash
python scripts/run_dashboard.py
```

Open the **运营日报** page to view equity, drawdown, admission-pool changes, probability drift, hit-rate tables and recent paper-trading decisions.

## Safety boundary

V3.0 is for research, local paper trading, and Demo/Testnet validation only. It does not submit live orders and does not authorize real-money trading.
