# V3.0.4 OKX WebSocket and Feature Sanitization Patch

This patch fixes two issues found during OKX migration testing.

## Fixes

1. OKX candlestick WebSocket subscriptions now default to the business WebSocket endpoint:
   `wss://ws.okx.com:8443/ws/v5/business`.
   OKX returns error `60018` when candle channels are subscribed on the public WebSocket path.

2. Feature construction now sanitizes non-finite numeric values by converting `+/-inf` to `NaN` before the existing `dropna`/imputation pipeline.
   This prevents scikit-learn errors such as `Input X contains infinity or a value too large for dtype('float64')`.

3. Added `scripts/check_dataset_nonfinite.py` for debugging feature columns with NaN/Inf values.

## Suggested commands

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"

python scripts/test_okx_ws.py --channel candle1m --inst-id BTC-USDT-SWAP
python scripts/build_features.py
python scripts/check_dataset_nonfinite.py
python scripts/train_model.py
```

Live trading remains disabled.
