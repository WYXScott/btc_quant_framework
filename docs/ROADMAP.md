# Roadmap

This roadmap turns the current framework into a complete quant trading system in controlled stages.

## Stage 1: Research Foundation

Status: mostly complete.

- Historical OHLCV download
- Data quality checks
- Feature generation
- Baseline model training
- Model diagnostics
- Walk-forward validation
- Probability calibration
- Strategy backtests
- Generated research reports

## Stage 2: Realtime Market Data

Status: V3.0.5 started.

- OKX WebSocket realtime candles
- SQLite realtime storage
- Realtime dashboard page
- Confirmed 4H merge path
- Reconnect/error status persistence

Next:

- background service wrapper
- data freshness alerts
- gap detection between REST and WebSocket candles
- automatic REST backfill after reconnect

## Stage 3: Robust Paper Trading

Status: partially complete.

- SQLite paper account
- paper order records
- target-exposure replay
- operations reports

Next:

- realtime candle driven paper loop
- daily state snapshot archive
- paper-vs-backtest drift report
- strategy disable/enable controls

## Stage 4: Strategy And Model Governance

Status: partially complete.

- model/strategy admission
- leaderboard
- calibration metrics
- overfit-risk metrics

Next:

- model registry metadata
- experiment manifest
- versioned candidate promotion
- stricter train/test data lineage

## Stage 5: Exchange Adapter Boundary

Status: partially complete.

- broker-neutral order intent
- Binance demo/testnet scaffolding
- execution safety guard
- order lifecycle and reconciliation

Next:

- OKX demo adapter
- exchange-agnostic execution adapter interface
- per-exchange capability matrix
- simulated exchange adapter for integration tests

## Stage 6: Live Readiness

Status: guarded and disabled by default.

- live safety gate
- kill switch
- hard circuit breaker
- read-only shadow mode
- pre-live manual workflow

Next:

- live-readiness audit bundle
- operator approval logs
- deployment runbook
- rollback and incident response docs

## Stage 7: Production Operations

Status: future.

- persistent service supervisor
- metrics export
- alert routing
- model/data freshness monitors
- deployment packaging
- secrets management integration
- disaster recovery checklist

