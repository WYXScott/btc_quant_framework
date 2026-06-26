from __future__ import annotations

import argparse
import json
from pathlib import Path
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.events import (
    parse_binance_user_data_event,
    sample_account_update_flat,
    sample_order_trade_update_fill,
)
from crypto_quant.exchange.sync import ExchangeStateSynchronizer
from crypto_quant.paper.database import PaperStore


def load_events(args: argparse.Namespace) -> list[dict]:
    if args.event_json:
        return [json.loads(args.event_json)]
    if args.file:
        path = Path(args.file)
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    return [sample_order_trade_update_fill(), sample_account_update_flat()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Binance user-data stream events into local audit tables.")
    parser.add_argument("--event-json", default=None, help="Single raw event JSON string.")
    parser.add_argument("--file", default=None, help="Path to a JSON event or list of events.")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path.")
    args = parser.parse_args()

    cfg = load_config()
    store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
    sync = ExchangeStateSynchronizer(cfg, store)

    output = []
    for raw in load_events(args):
        normalized = parse_binance_user_data_event(raw)
        for event in normalized:
            actions = sync.ingest_event(event)
            output.append({
                "event": event.to_dict(),
                "actions": [a.to_dict() for a in actions],
            })

    print(json.dumps({"num_records": len(output), "records": output}, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
