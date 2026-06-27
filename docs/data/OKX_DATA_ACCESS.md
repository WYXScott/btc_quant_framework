# OKX public market-data access

V3.0.3 switches the default public market-data source to OKX `BTC-USDT-SWAP`.

## Required network setup

If direct access to `www.okx.com` fails, set proxy environment variables in the same PowerShell window before running scripts:

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"
```

Check the active outlet:

```powershell
curl.exe https://ipinfo.io/json
```

## Connectivity checks

```powershell
python scripts/check_okx_connectivity.py
```

A successful response should include `code":"0"` for public time, ticker, candles, and history-candles.

## Download OKX BTC-USDT-SWAP candles

```powershell
python scripts/download_ohlcv.py
```

or explicitly:

```powershell
python scripts/download_okx_ohlcv.py
```

The default output is:

```text
data/raw/OKX_BTC_USDT_SWAP_4h.parquet
```

## Test OKX realtime WebSocket candles

```powershell
python scripts/test_okx_ws.py --channel candle1m --inst-id BTC-USDT-SWAP
```

If the proxy is not picked up automatically:

```powershell
python scripts/test_okx_ws.py --proxy http://127.0.0.1:7890 --channel candle1m --inst-id BTC-USDT-SWAP
```

## Safety boundary

This patch only changes public market data access. Private trading and live order submission remain disabled by default.
