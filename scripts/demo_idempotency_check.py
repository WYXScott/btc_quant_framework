from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.idempotency import IdempotencyStore, with_idempotent_client_order_id
from crypto_quant.exchange.order_intent import OrderIntent


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview deterministic clientOrderId/idempotency key generation.")
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--price", type=float, default=50000.0)
    parser.add_argument("--notional", type=float, default=20.0)
    parser.add_argument("--time-bucket", default="manual_demo_bucket")
    parser.add_argument("--reserve", action="store_true", help="Reserve the idempotency key locally; no exchange order is sent.")
    args = parser.parse_args()

    cfg = load_config()
    qty = args.notional / args.price
    intent = OrderIntent(
        symbol=str(cfg["symbol"]["ccxt_symbol"]),
        side=args.side,
        order_type="market",
        quantity=qty,
        leverage=float(cfg.get("trading", {}).get("leverage", 3.0)),
        reason="manual_idempotency_demo",
    )
    prefix = str(cfg.get("exchange_resilience", {}).get("client_order_prefix", "btcqv18"))
    safe_intent, key, fingerprint = with_idempotent_client_order_id(intent, prefix=prefix, time_bucket=args.time_bucket)
    payload = {
        "key": key,
        "fingerprint": fingerprint,
        "client_order_id": safe_intent.client_order_id,
        "intent": safe_intent.to_dict(),
        "reserved": False,
        "existing": None,
    }
    if args.reserve:
        db_path = resolve_path(cfg.get("exchange_resilience", {}).get("idempotency_db_path") or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
        store = IdempotencyStore(db_path)
        reserved, existing = store.reserve(
            key=key,
            client_order_id=str(safe_intent.client_order_id),
            fingerprint=fingerprint,
            intent=safe_intent.to_dict(),
        )
        payload["reserved"] = reserved
        payload["existing"] = None if existing is None else existing.to_dict()
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
