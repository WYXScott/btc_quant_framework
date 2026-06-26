from __future__ import annotations

import argparse
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.ensemble_runner import replay_ensemble_paper_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay historical ensemble target-exposure signals through local paper account.")
    parser.add_argument("--bars", type=int, default=200, help="Number of latest bars to replay; <=0 means full dataset.")
    parser.add_argument("--reset", action="store_true", help="Reset paper account before replay.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    args = parser.parse_args()

    cfg = load_config()
    db_path = resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    result = replay_ensemble_paper_dataset(cfg, bars=args.bars, reset=args.reset, db_path=db_path)
    print(result.tail(10).to_string(index=False))
    print(f"replayed_rows={len(result)}")


if __name__ == "__main__":
    main()
