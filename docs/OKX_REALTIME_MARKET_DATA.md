# OKX Realtime Market Data

V3.0.5 persists OKX public WebSocket candles to local SQLite.

## Default Config

```yaml
realtime:
  database_path: data/database/realtime_market.sqlite
  ws_url: wss://ws.okx.com:8443/ws/v5/business
  channels:
    - candle1m
    - candle4H
  auto_merge_history: true
  merge_channel: candle4H
  confirmed_only_merge: true
```

## Commands

Sample a few public messages:

```bash
python scripts/run_okx_realtime_listener.py --max-messages 5
```

Run a long-lived listener:

```bash
python scripts/run_okx_realtime_listener.py
```

Inspect the latest status and candles:

```bash
python scripts/run_realtime_status.py
```

Merge confirmed realtime 4H candles into the historical dataset:

```bash
python scripts/merge_realtime_ohlcv.py
```

## Tables

`realtime_klines` stores normalized OHLCV rows from OKX candle messages.

`realtime_status` stores the latest listener status, message counts and last error.

## Notes

- Only public market data is used.
- The default merge path uses confirmed `candle4H` rows only.
- `candle1m` is intended for realtime monitoring, not direct training dataset merges.
