from __future__ import annotations

import argparse
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Export paper-trading SQLite tables to CSV reports.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    parser.add_argument("--out", default="reports/paper_trading", help="Output directory for CSV reports.")
    args = parser.parse_args()

    cfg = load_config()
    db_path = resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    out_dir = resolve_path(args.out)
    store = PaperStore(db_path)
    paths = store.export_csvs(out_dir)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
