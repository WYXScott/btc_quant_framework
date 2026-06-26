# Binance restricted-location data workaround

If `fapi.binance.com` returns HTTP 451 or resets the connection, keep using Binance public market data through:

```yaml
download:
  downloader: binance_native
  base_url: https://data-api.binance.vision
```

This endpoint serves Binance public spot K-lines through `/api/v3/klines`. It is not USD-M futures data, but it allows the BTC low-frequency research, feature engineering, model training, calibration, and paper-trading pipeline to run when futures public endpoints are blocked.

To switch back to USD-M futures data later:

```yaml
download:
  base_url: https://fapi.binance.com
```

Then run:

```powershell
python scripts/check_binance_connectivity.py
python scripts/download_ohlcv.py
```
