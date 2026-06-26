from __future__ import annotations

import argparse
import json
import time
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.sync import ExchangeStateSynchronizer
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Polling-based Demo/Testnet reconciliation loop.")
    parser.add_argument("--fetch-private", action="store_true", help="Fetch private exchange snapshots. Requires API keys.")
    parser.add_argument("--interval-seconds", type=int, default=None, help="Override polling interval.")
    parser.add_argument("--max-iterations", type=int, default=1, help="Number of polling iterations. Default 1 for safety.")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path.")
    args = parser.parse_args()

    cfg = load_config()
    sync_cfg = cfg.get("sync", {})
    interval = int(args.interval_seconds or sync_cfg.get("poll_interval_seconds", 60))
    store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
    sync = ExchangeStateSynchronizer(cfg, store)

    for i in range(int(args.max_iterations)):
        report = sync.fetch_and_record_snapshot() if args.fetch_private else sync.build_offline_report()
        print(json.dumps({"iteration": i + 1, "report": report.to_dict()}, indent=2, ensure_ascii=False, default=str))
        if i < int(args.max_iterations) - 1:
            time.sleep(interval)


if __name__ == "__main__":
    main()
