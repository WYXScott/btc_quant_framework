from __future__ import annotations

import argparse
import json
from pathlib import Path
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.events import parse_binance_user_data_event
from crypto_quant.exchange.sync import ExchangeStateSynchronizer
from crypto_quant.paper.database import PaperStore


def sample_lifecycle_events() -> list[dict]:
    base = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1760000000000,
        "T": 1760000000000,
        "o": {
            "s": "BTCUSDT",
            "c": "btcqv19_entry_sample",
            "S": "BUY",
            "o": "MARKET",
            "f": "GTC",
            "q": "0.010",
            "p": "0",
            "ap": "0",
            "sp": "0",
            "i": 1900001,
            "l": "0",
            "z": "0",
            "L": "0",
            "R": False,
            "ps": "BOTH",
            "rp": "0",
        },
    }
    new = json.loads(json.dumps(base))
    new["o"].update({"x": "NEW", "X": "NEW"})
    part = json.loads(json.dumps(base))
    part["E"] += 1000
    part["o"].update({"x": "TRADE", "X": "PARTIALLY_FILLED", "l": "0.004", "z": "0.004", "L": "50000.0", "ap": "50000.0"})
    filled = json.loads(json.dumps(base))
    filled["E"] += 2000
    filled["o"].update({"x": "TRADE", "X": "FILLED", "l": "0.006", "z": "0.010", "L": "50100.0", "ap": "50060.0"})
    return [new, part, filled]


def load_events(path: str | None) -> list[dict]:
    if not path:
        return sample_lifecycle_events()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else [data]


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay order lifecycle events into V1.9 state-machine tables.")
    parser.add_argument("--file", default=None, help="Optional JSON file containing one event or a list of events.")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path.")
    args = parser.parse_args()

    cfg = load_config()
    store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
    sync = ExchangeStateSynchronizer(cfg, store)

    records = []
    for raw in load_events(args.file):
        for event in parse_binance_user_data_event(raw):
            actions = sync.ingest_event(event)
            records.append({"event": event.to_dict(), "actions": [a.to_dict() for a in actions]})

    print(json.dumps({"status": "ok", "num_events": len(records), "records": records}, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
