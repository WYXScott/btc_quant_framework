from __future__ import annotations

import argparse
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize or reset local paper-trading SQLite state.")
    parser.add_argument("--reset", action="store_true", help="Reset paper account, orders, decisions and equity curve.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    args = parser.parse_args()

    cfg = load_config()
    db_path = resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    store = PaperStore(db_path)

    if args.reset:
        account = store.reset(
            initial_equity=float(cfg["trading"]["initial_equity"]),
            leverage=float(cfg["trading"]["leverage"]),
        )
        print(f"Paper account reset: db={db_path}")
    else:
        account = store.load_account(
            initial_equity=float(cfg["trading"]["initial_equity"]),
            leverage=float(cfg["trading"]["leverage"]),
        )
        print(f"Paper account initialized/loaded: db={db_path}")

    print(account)


if __name__ == "__main__":
    main()
