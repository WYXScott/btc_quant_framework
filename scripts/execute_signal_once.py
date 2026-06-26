from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.runner import run_paper_step


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute one latest strategy signal through a selected execution bridge.")
    parser.add_argument("--mode", choices=["local_paper", "binance_futures_demo"], default=None,
                        help="Execution backend. Defaults to config execution.mode.")
    parser.add_argument("--update-data", action="store_true", help="Update public OHLCV data before deciding.")
    parser.add_argument("--allow-repeat", action="store_true", help="Allow reprocessing the latest candle.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    parser.add_argument("--execute", action="store_true",
                        help="Only meaningful for binance_futures_demo; submits a testnet order if confirmed.")
    parser.add_argument("--confirm", default=None, help="Required confirmation phrase for testnet order submission.")
    args = parser.parse_args()

    cfg = load_config()
    if args.mode:
        cfg.setdefault("execution", {})["mode"] = args.mode
    db_path = resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    result = run_paper_step(
        cfg,
        db_path=db_path,
        update_data=args.update_data,
        new_candle_only=not args.allow_repeat,
        execution_mode=cfg.get("execution", {}).get("mode", "local_paper"),
        execute=args.execute,
        confirmation=args.confirm,
    )
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
