from __future__ import annotations

import _bootstrap  # noqa: F401

import argparse
import json
import os
from urllib.parse import urlparse

import websocket


def _proxy_kwargs(proxy_url: str | None) -> dict:
    proxy_url = proxy_url or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not proxy_url:
        return {}
    parsed = urlparse(proxy_url)
    if not parsed.hostname or not parsed.port:
        return {}
    proxy_type = "socks5" if parsed.scheme.startswith("socks") else "http"
    kwargs = {
        "http_proxy_host": parsed.hostname,
        "http_proxy_port": parsed.port,
        "proxy_type": proxy_type,
    }
    if parsed.username:
        kwargs["http_proxy_auth"] = (parsed.username, parsed.password or "")
    return kwargs


def main() -> None:
    parser = argparse.ArgumentParser(description="Test OKX public WebSocket candles.")
    parser.add_argument("--inst-id", default="BTC-USDT-SWAP")
    parser.add_argument("--channel", default="candle1m")
    parser.add_argument("--url", default=None, help="WebSocket URL. Defaults to OKX business WS for candle* channels, otherwise public WS.")
    parser.add_argument("--proxy", default=None, help="Optional proxy URL, e.g. http://127.0.0.1:7890")
    parser.add_argument("--max-messages", type=int, default=2)
    args = parser.parse_args()

    if args.url:
        ws_url = args.url
    elif str(args.channel).startswith("candle"):
        # OKX candlestick channels are served from the business WebSocket path.
        ws_url = "wss://ws.okx.com:8443/ws/v5/business"
    else:
        ws_url = "wss://ws.okx.com:8443/ws/v5/public"

    count = {"n": 0}
    subscribe_payload = {
        "op": "subscribe",
        "args": [{"channel": args.channel, "instId": args.inst_id}],
    }

    def on_open(ws):
        print("opened")
        ws.send(json.dumps(subscribe_payload))
        print({"sent": subscribe_payload})

    def on_message(ws, message):
        count["n"] += 1
        try:
            data = json.loads(message)
        except Exception:
            data = message
        print({"message_index": count["n"], "message": data})
        if count["n"] >= args.max_messages:
            ws.close()

    def on_error(ws, error):
        print("error:", repr(error))

    def on_close(ws, code, msg):
        print("closed:", code, msg)

    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    print({"url": ws_url})
    kwargs = _proxy_kwargs(args.proxy)
    if kwargs:
        print({"proxy": kwargs})
    ws.run_forever(ping_interval=20, ping_timeout=10, **kwargs)


if __name__ == "__main__":
    main()
