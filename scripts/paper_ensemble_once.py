from __future__ import annotations

import argparse
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.ensemble_runner import run_ensemble_paper_step


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute one local ensemble dynamic-exposure paper step.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    parser.add_argument("--allow-repeat", action="store_true", help="Allow processing the same latest candle again.")
    args = parser.parse_args()

    cfg = load_config()
    db_path = resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    result = run_ensemble_paper_step(cfg, db_path=db_path, new_candle_only=not args.allow_repeat)
    print("ensemble paper step result:")
    print(result.to_dict())
    if result.order:
        print("order:")
        print(result.order)


if __name__ == "__main__":
    main()
