from __future__ import annotations

import _bootstrap  # noqa: F401

import os
import time
import requests


def env_proxy_snapshot() -> dict[str, str | None]:
    return {
        "HTTP_PROXY": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "HTTPS_PROXY": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
    }


def probe(url: str, timeout: float = 8.0) -> dict:
    started = time.time()
    try:
        resp = requests.get(url, timeout=timeout)
        preview = resp.text[:300].replace("\n", " ")
        return {
            "url": url,
            "ok": resp.ok,
            "status_code": resp.status_code,
            "elapsed_seconds": round(time.time() - started, 3),
            "preview": preview,
        }
    except Exception as exc:
        return {
            "url": url,
            "ok": False,
            "status_code": None,
            "elapsed_seconds": round(time.time() - started, 3),
            "error": repr(exc),
        }


def main() -> None:
    print({"proxy_env": env_proxy_snapshot()})
    urls = [
        "https://www.okx.com/api/v5/public/time",
        "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP",
        "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=4H&limit=2",
        "https://www.okx.com/api/v5/market/history-candles?instId=BTC-USDT-SWAP&bar=4H&limit=2",
    ]
    for url in urls:
        print(probe(url))


if __name__ == "__main__":
    main()
