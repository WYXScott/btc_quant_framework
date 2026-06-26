# BTC Quant Framework V3.0.5

V3.0.5 adds OKX realtime public market-data persistence.

## Added

- OKX WebSocket candle listener for `candle1m` and `candle4H`.
- Local SQLite storage tables:
  - `realtime_klines`
  - `realtime_status`
- Idempotent realtime kline upsert keyed by exchange, instrument, channel and timestamp.
- Confirmed `candle4H` merge path back into the historical 4H parquet dataset.
- Streamlit **实时行情** page for latest price, status, recent candles and close chart.
- CLI scripts:
  - `scripts/run_okx_realtime_listener.py`
  - `scripts/run_realtime_status.py`
  - `scripts/merge_realtime_ohlcv.py`

## Safety

- Public market data only.
- No trading keys are required.
- No live order submission path is added.
- Historical merge defaults to confirmed candles only.

## Validation

- Added smoke coverage for OKX candle parsing, SQLite upsert, status persistence and historical merge.
