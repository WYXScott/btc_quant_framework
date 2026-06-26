from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.runner import run_paper_step


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one stateful paper-trading decision on the latest BTC candle.")
    parser.add_argument("--update-data", action="store_true", help="Update public OHLCV data and rebuild features before deciding.")
    parser.add_argument("--allow-repeat", action="store_true", help="Allow reprocessing the latest candle. Default skips duplicates.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    args = parser.parse_args()

    cfg = load_config()
    cfg.setdefault("execution", {})["mode"] = "local_paper"
    db_path = resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    result = run_paper_step(
        cfg,
        db_path=db_path,
        update_data=args.update_data,
        new_candle_only=not args.allow_repeat,
        execution_mode="local_paper",
    )
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
