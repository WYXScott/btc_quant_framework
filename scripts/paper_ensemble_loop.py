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
    parser.add_argument("--max-consecutive-errors", type=int, default=None, help="Stop after this many consecutive failures. Default from config paper.max_consecutive_errors.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    args = parser.parse_args()

    cfg = load_config()
    paper_cfg = cfg.get("paper", {})
    interval = int(args.interval_seconds or paper_cfg.get("run_interval_seconds", 14400))
    max_errors = int(args.max_consecutive_errors if args.max_consecutive_errors is not None else paper_cfg.get("max_consecutive_errors", 3))
    db_path = resolve_path(args.db or paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))

    i = 0
    consecutive_errors = 0
    while True:
        i += 1
        try:
            result = run_ensemble_paper_step(cfg, db_path=db_path, new_candle_only=True)
            consecutive_errors = 0
            print(result.to_dict(), flush=True)
            if result.order:
                print(f"order={result.order}", flush=True)
        except Exception as exc:
            consecutive_errors += 1
            print(
                f"paper_ensemble_loop_error={type(exc).__name__}: {exc}; "
                f"consecutive_errors={consecutive_errors}/{max_errors}",
                flush=True,
            )
            if max_errors > 0 and consecutive_errors >= max_errors:
                raise SystemExit(1) from exc

        if args.max_iterations and i >= args.max_iterations:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
