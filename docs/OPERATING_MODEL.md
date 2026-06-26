# Operating Model

This document describes how the system should be operated as it grows from research to paper trading and eventually controlled live-readiness workflows.

## Modes

## Research Mode

Purpose: build datasets, train models, validate strategies and generate reports.

Typical commands:

```bash
python scripts/download_ohlcv.py
python scripts/run_data_quality_check.py
python scripts/build_features.py
python scripts/train_model.py
python scripts/run_walk_forward_calibration.py
python scripts/run_strategy_parameter_search.py
python scripts/run_ensemble_strategy.py
```

Expected outputs:

- `data/raw/*.parquet`
- `data/processed/*.parquet`
- `models/*.joblib`
- `reports/**`

These outputs are local artifacts and are ignored by Git.

## Realtime Data Mode

Purpose: persist public OKX realtime candles and monitor data freshness.

Typical commands:

```bash
python scripts/run_okx_realtime_listener.py
python scripts/run_realtime_status.py
python scripts/merge_realtime_ohlcv.py
```

Expected outputs:

- `data/database/realtime_market.sqlite`
- `realtime_klines`
- `realtime_status`

## Local Paper Mode

Purpose: replay target exposure or run local paper decisions without touching an exchange.

Typical commands:

```bash
python scripts/paper_init.py --reset
python scripts/paper_ensemble_replay_dataset.py --bars 300 --reset
python scripts/run_paper_health_check.py
python scripts/run_daily_operations_report.py
```

Expected outputs:

- `data/database/paper_trading.sqlite`
- operations reports under `reports/operations`

## Demo/Testnet Mode

Purpose: preview or test guarded order-intent conversion against an exchange-like adapter.

Rules:

- Keep dry-run enabled by default.
- Require explicit script flags before any testnet submission.
- Require confirmation phrases for unsafe operations.
- Persist order lifecycle and reconciliation records.

## Live Readiness Mode

Purpose: evaluate whether the system is ready for manual go-live review.

Rules:

- Live trading remains blocked unless multiple safety switches are changed.
- Read-only shadow checks are allowed.
- Pre-live checklist and API permission audit must pass before considering live actions.
- Human review remains mandatory.

## Daily Operator Checklist

1. Check realtime market-data freshness.
2. Check data quality before retraining.
3. Review latest model/strategy admission report.
4. Review paper equity and drawdown.
5. Review operations alerts.
6. Confirm safety gate remains blocked unless intentionally entering review mode.

