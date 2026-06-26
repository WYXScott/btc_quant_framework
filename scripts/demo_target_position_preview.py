from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config
from crypto_quant.exchange.target_position import build_target_position_plan
from crypto_quant.exchange.target_execution import execute_target_position_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview a manual target-exposure rebalance plan for Binance Futures Demo/Testnet.")
    parser.add_argument("--price", type=float, required=True, help="Reference BTC price.")
    parser.add_argument("--equity", type=float, default=None, help="Account equity in USDT. Defaults to config trading.initial_equity.")
    parser.add_argument("--current-qty", type=float, default=0.0, help="Current long BTC quantity.")
    parser.add_argument("--target-exposure", type=float, required=True, help="Target notional exposure / equity, e.g. 0, 1, 3.")
    parser.add_argument("--no-demo-cap", action="store_true", help="Do not cap by broker.safety.max_order_notional_usdt in preview.")
    parser.add_argument("--with-protection", action="store_true", help="Also generate native SL/TP protection intents.")
    parser.add_argument("--execute", action="store_true", help="Submit to Demo/Testnet. Default is dry-run preview.")
    parser.add_argument("--confirm", default=None, help="Required confirmation phrase for --execute.")
    args = parser.parse_args()

    cfg = load_config()
    equity = float(args.equity if args.equity is not None else cfg["trading"].get("initial_equity", 1000.0))
    plan = build_target_position_plan(
        cfg,
        reference_price=float(args.price),
        equity_usdt=equity,
        target_exposure=float(args.target_exposure),
        current_qty=float(args.current_qty),
        timestamp="manual_target_position_preview",
        reason="manual_target_position_preview",
        apply_demo_order_cap=not args.no_demo_cap,
        include_protective_plan=args.with_protection,
    )
    result = execute_target_position_plan(cfg, plan, execute=args.execute, confirmation=args.confirm)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
