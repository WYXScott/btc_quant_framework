from __future__ import annotations

import argparse
import time
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.ensemble_runner import run_ensemble_paper_step


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ensemble dynamic-exposure paper trading repeatedly.")
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
            result = run_ensemble_paper_step(cfg, db_path=db_path, new_candle_only=True)
            print(result.to_dict())
            if result.order:
                print(f"order={result.order}")
        except Exception as exc:
            print(f"paper_ensemble_loop_error={type(exc).__name__}: {exc}")

        if args.max_iterations and i >= args.max_iterations:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
