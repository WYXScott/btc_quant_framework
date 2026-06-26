from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.cancel_recovery import build_cancel_failure_plan
from crypto_quant.paper.database import PaperStore


class SimulatedExchangeError(Exception):
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview V1.9 cancel-failure recovery plan.")
    parser.add_argument("--category", default="network_error", help="Simulated error category, e.g. order_not_found/network_error/invalid_order.")
    parser.add_argument("--order-id", default="1900001")
    parser.add_argument("--client-order-id", default="btcqv19_sl_sample")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    # Keep this demo deterministic instead of relying on CCXT exception classes.
    plan = build_cancel_failure_plan(
        None,
        order_id=args.order_id,
        client_order_id=args.client_order_id,
        exchange_response={
            "error_category": args.category,
            "retryable": args.category in {"network_error", "rate_limited", "exchange_not_available", "request_timeout", "temporary_exchange_error"},
            "message": f"Simulated cancel failure: {args.category}",
        },
    )
    result = plan.to_dict()
    if args.persist:
        cfg = load_config()
        store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
        store.append_cancel_failure_event(result)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
