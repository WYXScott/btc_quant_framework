from __future__ import annotations

import argparse
from pathlib import Path
import shutil

import pandas as pd
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet, save_parquet
from crypto_quant.paper.database import PaperStore
from crypto_quant.paper.runner import run_paper_step


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay the latest N rows of the local dataset through the stateful paper engine. Useful for debugging database state."
    )
    parser.add_argument("--bars", type=int, default=120, help="Number of latest bars to replay.")
    parser.add_argument("--reset", action="store_true", help="Reset the paper database before replay.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    args = parser.parse_args()

    cfg = load_config()
    dataset_path = resolve_path(cfg["data"]["dataset_path"])
    backup_path = dataset_path.with_suffix(dataset_path.suffix + ".replay_backup")
    db_path = resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))

    df = load_parquet(dataset_path)
    replay = df.tail(args.bars).copy()
    if args.reset:
        PaperStore(db_path).reset(float(cfg["trading"]["initial_equity"]), float(cfg["trading"]["leverage"]))

    # The paper runner consumes the configured dataset path and always reads the latest row.
    # To replay without changing feature-generation code, temporarily write expanding slices.
    shutil.copy2(dataset_path, backup_path)
    try:
        for i in range(1, len(replay) + 1):
            save_parquet(replay.iloc[:i], dataset_path)
            result = run_paper_step(cfg, db_path=db_path, update_data=False, new_candle_only=True)
            print(result)
    finally:
        shutil.move(backup_path, dataset_path)

    print(f"Replay finished. Export with: python scripts/paper_export_report.py --db {db_path}")


if __name__ == "__main__":
    main()
