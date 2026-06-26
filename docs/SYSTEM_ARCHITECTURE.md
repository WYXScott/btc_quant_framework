# System Architecture

BTC Quant Framework is organized as a layered trading-system research stack. The default runtime is intentionally conservative: public data, local research, local paper trading, and safety checks. Real-money automated trading is not enabled by default.

## Layered Model

```text
Market Data
  REST historical candles
  WebSocket realtime candles
  parquet and SQLite storage

Research Data
  quality checks
  feature generation
  labels and train/test datasets

Models And Signals
  model training
  probability calibration
  walk-forward prediction
  strategy signals
  ensemble target exposure

Risk And Admission
  model/strategy admission
  risk manager
  circuit breakers
  live gate

Execution
  broker-neutral decisions
  broker-neutral order intents
  local paper broker
  demo/testnet adapters
  reconciliation and order lifecycle

Operations
  SQLite paper state
  daily reports
  realtime status
  Streamlit dashboard
  pre-live review workflow
```

## Current Boundaries

- `src/crypto_quant/data`: public data downloads, realtime data ingestion, parquet utilities.
- `src/crypto_quant/features`: OHLCV feature engineering and labels.
- `src/crypto_quant/models`: model training, prediction, calibration, walk-forward logic.
- `src/crypto_quant/strategy`: rule and ML signal generation.
- `src/crypto_quant/research`: diagnostics, model libraries, robustness, ensembles, admission.
- `src/crypto_quant/backtest`: fixed leverage and dynamic target-exposure backtest engines.
- `src/crypto_quant/paper`: SQLite-backed local paper account, broker, runner, replay.
- `src/crypto_quant/execution`: strategy decisions and broker-neutral execution bridge.
- `src/crypto_quant/exchange`: exchange-facing order intent, safety, recovery, sync, lifecycle.
- `src/crypto_quant/live`: live safety gate, kill switch, read-only shadow and pre-live workflow.
- `src/crypto_quant/ops`: operations reports and daily health summaries.
- `src/crypto_quant/ui`: dashboard helper functions.
- `src/crypto_quant/interfaces`: forward-looking contracts for future providers and adapters.

## Data Flow

```text
OKX REST/WebSocket
      |
      v
raw OHLCV parquet / realtime SQLite
      |
      v
quality checks -> features -> labels -> dataset parquet
      |
      v
models -> calibrated probabilities -> strategy signals
      |
      v
walk-forward validation / backtests / model-strategy admission
      |
      v
ensemble target exposure
      |
      v
local paper trading -> operations reports -> dashboard
```

## Design Principles

- Separate research signals from order execution.
- Treat exchange access as an adapter boundary.
- Keep all real-money actions behind explicit safety gates.
- Persist operational state in SQLite for inspectability.
- Keep generated data, models, logs and reports out of Git.
- Prefer small CLI scripts over hidden side effects.
- Preserve reproducible research paths before adding automation.

