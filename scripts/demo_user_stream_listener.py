from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.events import parse_binance_user_data_event
from crypto_quant.exchange.sync import ExchangeStateSynchronizer
from crypto_quant.exchange.user_stream import BinanceFuturesUserDataStream
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Listen to a Binance USD-M Futures user-data websocket and write normalized events locally."
    )
    parser.add_argument("--listen-key", required=True, help="Listen key returned by demo_user_stream_check.py --execute.")
    parser.add_argument("--max-messages", type=int, default=10, help="Stop after this many websocket messages. Use cautiously.")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path.")
    args = parser.parse_args()

    try:
        import websocket  # type: ignore
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "websocket-client is required for websocket listening. Install dependencies with: pip install -r requirements.txt"
        ) from exc

    cfg = load_config()
    stream = BinanceFuturesUserDataStream(cfg, require_private=False)
    ws_url = stream.build_websocket_url(args.listen_key)
    store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
    sync = ExchangeStateSynchronizer(cfg, store)

    counter = {"n": 0}

    def on_message(ws, message: str) -> None:  # noqa: ANN001
        counter["n"] += 1
        raw = json.loads(message)
        records = []
        for event in parse_binance_user_data_event(raw):
            actions = sync.ingest_event(event)
            records.append({"event": event.to_dict(), "actions": [a.to_dict() for a in actions]})
        print(json.dumps({"message_index": counter["n"], "records": records}, ensure_ascii=False, default=str))
        if counter["n"] >= args.max_messages:
            ws.close()

    def on_error(ws, error) -> None:  # noqa: ANN001
        print(json.dumps({"status": "websocket_error", "error": str(error)}, ensure_ascii=False))

    def on_close(ws, close_status_code, close_msg) -> None:  # noqa: ANN001
        print(json.dumps({"status": "websocket_closed", "code": close_status_code, "message": close_msg}, ensure_ascii=False))

    print(json.dumps({"status": "connecting", "url": ws_url, "max_messages": args.max_messages}, ensure_ascii=False))
    app = websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error, on_close=on_close)
    app.run_forever(ping_interval=20, ping_timeout=10)


if __name__ == "__main__":
    main()
