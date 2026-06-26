from __future__ import annotations

import argparse
import uuid
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.execution.order_lifecycle import OrderLifecycleSimulator, PendingOrder
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Demonstrate local limit/stop pending-order timeout/fill simulation.")
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--order-type", choices=["limit", "stop_market"], default="limit")
    parser.add_argument("--price", type=float, default=50000.0)
    parser.add_argument("--qty", type=float, default=0.001)
    parser.add_argument("--bar-high", type=float, default=50100.0)
    parser.add_argument("--bar-low", type=float, default=49900.0)
    parser.add_argument("--timestamp", default="2026-01-01 00:00:00+00:00")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    cfg = load_config()
    sim = OrderLifecycleSimulator(
        max_order_age_bars=int(cfg.get("pending_orders", {}).get("max_order_age_bars", 1)),
        slippage_rate=float(cfg["trading"].get("slippage_rate", 0.0005)),
    )
    order = PendingOrder(
        order_id="demo_" + uuid.uuid4().hex[:10],
        created_timestamp=args.timestamp,
        side=args.side,
        order_type=args.order_type,
        price=args.price,
        qty=args.qty,
        reason="manual_lifecycle_demo",
    )
    updated = sim.update(order, timestamp=args.timestamp, high=args.bar_high, low=args.bar_low)
    payload = updated.to_dict()
    payload["last_update_timestamp"] = args.timestamp

    db_path = resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    PaperStore(db_path).upsert_pending_order(payload)
    print(payload)


if __name__ == "__main__":
    main()
