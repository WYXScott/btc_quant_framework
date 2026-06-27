# Release Notes V3.0

## Long-run paper operations and daily research reports

V3.0 adds an operations layer focused on long-running paper/demo validation:

- Daily operations report.
- Paper health check.
- Signal hit-rate report.
- Admission-pool snapshot and change detection.
- Probability drift monitoring.
- Equity and drawdown charts.
- Streamlit frontend page: `运营日报`.

## New scripts

```bash
python scripts/run_paper_health_check.py
python scripts/run_signal_hit_rate_report.py
python scripts/run_daily_operations_report.py
python scripts/build_v30_operations_report.py
python scripts/operations_smoke.py
```

## New modules

```text
src/crypto_quant/ops/daily_report.py
```

## Safety

No live trading is enabled. V3.0 is a monitoring and reporting layer for paper trading, research and Demo/Testnet validation.
