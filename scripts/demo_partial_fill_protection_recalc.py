from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.partial_fill import build_protection_recalc_plan
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview V1.9 protective-order recalculation after partial fills.")
    parser.add_argument("--position-qty", type=float, default=0.004, help="Current filled/position quantity.")
    parser.add_argument("--entry-price", type=float, default=50000.0, help="Entry/average fill price.")
    parser.add_argument("--existing-protection-qty", type=float, default=0.0, help="Existing reduce-only protection quantity.")
    parser.add_argument("--persist", action="store_true", help="Persist plan to SQLite diagnostic table.")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    cfg = load_config()
    open_orders = []
    if args.existing_protection_qty > 0:
        open_orders.append({
            "type": "STOP_MARKET",
            "reduceOnly": True,
            "remaining": float(args.existing_protection_qty),
            "info": {"reduceOnly": True, "origQty": str(args.existing_protection_qty)},
        })
    plan = build_protection_recalc_plan(
        symbol=str(cfg.get("symbol", {}).get("ccxt_symbol", "BTC/USDT:USDT")),
        position_qty=float(args.position_qty),
        entry_price=float(args.entry_price),
        open_orders=open_orders,
        cfg=cfg,
        attach_new_intents=True,
    )
    result = plan.to_dict()
    if args.persist:
        store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
        store.append_protection_recalc_plan(result)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
