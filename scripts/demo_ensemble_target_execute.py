from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config
from crypto_quant.exchange.target_execution import latest_ensemble_target_preview, execute_target_position_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or submit latest ensemble target-position intents to Binance Futures Demo/Testnet.")
    parser.add_argument("--source", choices=["local_paper", "manual"], default="local_paper")
    parser.add_argument("--current-qty", type=float, default=None, help="Manual/current exchange long BTC quantity override.")
    parser.add_argument("--equity", type=float, default=None, help="Manual/effective account equity override in USDT.")
    parser.add_argument("--no-demo-cap", action="store_true", help="Do not cap by broker.safety.max_order_notional_usdt in preview.")
    parser.add_argument("--with-protection", action="store_true", help="Also generate native SL/TP protection intents.")
    parser.add_argument("--execute", action="store_true", help="Submit to Demo/Testnet. Default is dry-run preview.")
    parser.add_argument("--confirm", default=None, help="Required confirmation phrase for --execute.")
    args = parser.parse_args()

    cfg = load_config()
    preview = latest_ensemble_target_preview(
        cfg,
        current_qty=args.current_qty,
        equity_usdt=args.equity,
        source=args.source,
        apply_demo_order_cap=not args.no_demo_cap,
        include_protective_plan=args.with_protection,
    )
    result = execute_target_position_plan(cfg, preview.plan, execute=args.execute, confirmation=args.confirm)
    payload = {"preview": preview.to_dict(), "execution_result": result.to_dict()}
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
