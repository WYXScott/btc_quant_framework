from __future__ import annotations

import argparse
import time
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.runner import run_paper_step


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paper trading repeatedly with persistent SQLite state.")
    parser.add_argument("--update-data", action="store_true", help="Update public OHLCV data before each decision.")
    parser.add_argument("--interval-seconds", type=int, default=None, help="Override loop interval. Default from config.")
    parser.add_argument("--max-iterations", type=int, default=0, help="0 means run forever; positive value limits loop count.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    args = parser.parse_args()

    cfg = load_config()
    paper_cfg = cfg.get("paper", {})
    interval = int(args.interval_seconds or paper_cfg.get("run_interval_seconds", 14400))
    db_path = resolve_path(args.db or paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))

    i = 0
    while True:
        i += 1
        try:
            result = run_paper_step(cfg, db_path=db_path, update_data=args.update_data, new_candle_only=True)
            print(result)
            if result.order:
                print(f"order={result.order}")
        except Exception as exc:  # deliberately broad for long-running paper loop
            print(f"paper_loop_error={type(exc).__name__}: {exc}")

        if args.max_iterations and i >= args.max_iterations:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
