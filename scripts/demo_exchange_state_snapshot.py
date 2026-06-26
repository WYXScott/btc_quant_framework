from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config
from crypto_quant.exchange.synced_target_execution import build_offline_synced_state, fetch_synced_state


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview/fetch Binance Futures Demo/Testnet execution state snapshot.")
    parser.add_argument("--fetch-private", action="store_true", help="Fetch real Demo/Testnet private snapshot using testnet API keys.")
    parser.add_argument("--exchange-qty", type=float, default=0.0, help="Offline simulated exchange position qty.")
    parser.add_argument("--equity", type=float, default=None, help="Offline simulated USDT equity.")
    parser.add_argument("--open-order-count", type=int, default=0, help="Offline simulated protective open order count.")
    parser.add_argument("--mark-price", type=float, default=None, help="Offline simulated mark/reference price.")
    args = parser.parse_args()

    cfg = load_config()
    if args.fetch_private:
        state = fetch_synced_state(cfg)
    else:
        state = build_offline_synced_state(
            cfg,
            exchange_qty=args.exchange_qty,
            equity_usdt=args.equity,
            open_order_count=args.open_order_count,
            mark_price=args.mark_price,
        )
    print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
