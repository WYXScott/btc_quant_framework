from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config
from crypto_quant.exchange.target_execution import latest_ensemble_target_preview


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview latest ensemble target exposure as Demo/Testnet order intents.")
    parser.add_argument("--source", choices=["local_paper", "manual"], default="local_paper")
    parser.add_argument("--current-qty", type=float, default=None, help="Manual/current exchange long BTC quantity override.")
    parser.add_argument("--equity", type=float, default=None, help="Manual/effective account equity override in USDT.")
    parser.add_argument("--no-demo-cap", action="store_true", help="Do not cap by broker.safety.max_order_notional_usdt in preview.")
    parser.add_argument("--with-protection", action="store_true", help="Also generate native SL/TP protection intents.")
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
    print(json.dumps(preview.to_dict(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
