from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config
from crypto_quant.exchange.order_intent import OrderIntent
from crypto_quant.exchange.resilient_executor import ResilientExchangeExecutor


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or submit a tiny idempotent/retry-aware Binance Futures Demo order.")
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--price", type=float, default=50000.0)
    parser.add_argument("--notional", type=float, default=20.0)
    parser.add_argument("--time-bucket", default=None, help="Stable bucket for idempotency, e.g. candle timestamp.")
    parser.add_argument("--reduce-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args()

    cfg = load_config()
    qty = args.notional / args.price
    intent = OrderIntent(
        symbol=str(cfg["symbol"]["ccxt_symbol"]),
        side=args.side,
        order_type="market",
        quantity=qty,
        reduce_only=args.reduce_only,
        leverage=float(cfg.get("trading", {}).get("leverage", 3.0)),
        reason="manual_resilient_order_demo",
    )
    executor = ResilientExchangeExecutor(cfg)
    result = executor.submit_intent(
        intent,
        reference_price=args.price,
        execute=args.execute,
        confirmation=args.confirm,
        time_bucket=args.time_bucket,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
