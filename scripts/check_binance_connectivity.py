from __future__ import annotations

import os
import time
import requests
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config


def _proxy_summary() -> dict[str, str | None]:
    return {
        "HTTP_PROXY": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "HTTPS_PROXY": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
    }


def check_url(url: str, timeout: float = 10.0) -> dict:
    started = time.time()
    try:
        r = requests.get(url, timeout=timeout)
        elapsed = round(time.time() - started, 3)
        ok = 200 <= r.status_code < 300
        text = r.text[:200]
        return {"url": url, "ok": ok, "status_code": r.status_code, "elapsed_seconds": elapsed, "preview": text}
    except Exception as exc:
        elapsed = round(time.time() - started, 3)
        return {"url": url, "ok": False, "status_code": None, "elapsed_seconds": elapsed, "error": repr(exc)}


def main() -> None:
    cfg = load_config()
    timeout = float(cfg.get("download", {}).get("timeout_seconds", 10.0))
    symbol = cfg.get("symbol", {}).get("raw_symbol", "BTCUSDT")
    interval = cfg.get("data", {}).get("timeframe", "4h")
    futures_base = cfg.get("download", {}).get("base_url") or "https://fapi.binance.com"
    spot_market_base = "https://data-api.binance.vision"
    urls = [
        f"{futures_base}/fapi/v1/time",
        f"{futures_base}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit=2",
        f"{spot_market_base}/api/v3/klines?symbol={symbol}&interval={interval}&limit=2",
    ]
    print({"proxy_env": _proxy_summary()})
    results = []
    for url in urls:
        result = check_url(url, timeout=timeout)
        results.append(result)
        print(result)

    print({
        "recommendation": (
            "If fapi.binance.com is blocked but data-api.binance.vision is ok, "
            "keep config download.base_url=https://data-api.binance.vision and run scripts/download_ohlcv.py. "
            "This uses Binance public spot klines to continue research and model training."
        )
    })


if __name__ == "__main__":
    main()
