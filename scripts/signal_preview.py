from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.runner import latest_decision_preview


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview the latest BTC strategy decision and broker-neutral OrderIntent.")
    parser.add_argument("--update-data", action="store_true", help="Update OHLCV/features before previewing.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    parser.add_argument("--mode", choices=["local_paper", "binance_futures_demo"], default=None)
    args = parser.parse_args()

    cfg = load_config()
    if args.mode:
        cfg.setdefault("execution", {})["mode"] = args.mode
    db_path = resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    decision, intent, account = latest_decision_preview(cfg, db_path=db_path, update_data=args.update_data)
    payload = {
        "execution_mode": cfg.get("execution", {}).get("mode", "local_paper"),
        "account": {
            "equity": account.equity,
            "cash": account.cash,
            "position_qty": account.position_qty,
            "entry_price": account.entry_price,
            "leverage": account.leverage,
        },
        "decision": decision.to_dict(),
        "order_intent": intent,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
