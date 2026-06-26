from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.sync import ExchangeStateSynchronizer
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one local/exchange reconciliation pass.")
    parser.add_argument("--fetch-private", action="store_true", help="Fetch private Demo/Testnet position and open orders. Requires API keys.")
    parser.add_argument("--exchange-qty", type=float, default=None, help="Offline simulated exchange position quantity.")
    parser.add_argument("--open-order-count", type=int, default=None, help="Offline simulated exchange open-order count.")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path.")
    args = parser.parse_args()

    cfg = load_config()
    store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
    sync = ExchangeStateSynchronizer(cfg, store)
    if args.fetch_private:
        report = sync.fetch_and_record_snapshot()
    else:
        report = sync.build_offline_report(exchange_qty=args.exchange_qty, open_order_count=args.open_order_count)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
