from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from _bootstrap import ROOT  # noqa: E402,F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker
from crypto_quant.exchange.recovery import ExchangePositionSnapshot, compare_local_and_exchange_state
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare local paper state with Binance Futures Demo/Testnet state.")
    parser.add_argument("--fetch-private", action="store_true", help="Fetch real Demo/Testnet position and open orders. Requires API keys.")
    parser.add_argument("--exchange-qty", type=float, default=None, help="Offline simulated exchange position quantity.")
    parser.add_argument("--open-order-count", type=int, default=None, help="Offline simulated number of open protective orders.")
    args = parser.parse_args()

    cfg = load_config()
    store = PaperStore(resolve_path(cfg["paper"]["database_path"]))
    account = store.load_account(
        initial_equity=float(cfg["trading"]["initial_equity"]),
        leverage=float(cfg["trading"]["leverage"]),
    )

    exchange_position = None
    open_orders = None
    source = "local_only"

    if args.fetch_private:
        broker = BinanceFuturesDemoBroker(cfg, require_private=True)
        exchange_position = broker.fetch_position_snapshot()
        open_orders = broker.fetch_open_orders_snapshot()
        source = "binance_futures_demo_private"
    elif args.exchange_qty is not None:
        exchange_position = ExchangePositionSnapshot(
            symbol=str(cfg["symbol"]["ccxt_symbol"]),
            contracts=float(args.exchange_qty),
            side="long" if args.exchange_qty > 0 else None,
            entry_price=None,
            notional=None,
            raw={"offline_simulated": True},
        )
        count = int(args.open_order_count or 0)
        open_orders = [{"type": "STOP_MARKET", "reduceOnly": True} for _ in range(count)]
        source = "offline_simulated_exchange"

    result = compare_local_and_exchange_state(
        local_account=account,
        exchange_position=exchange_position,
        open_orders=open_orders,
        min_protective_order_count=int(cfg.get("native_protection", {}).get("min_protective_order_count", 1)),
    )

    print(json.dumps({
        "source": source,
        "local_account": {
            "in_position": account.in_position,
            "position_qty": account.position_qty,
            "entry_price": account.entry_price,
            "equity": account.equity,
            "stop_loss_price": account.stop_loss_price,
            "take_profit_price": account.take_profit_price,
            "trailing_stop_price": account.trailing_stop_price,
        },
        "exchange_position": None if exchange_position is None else exchange_position.to_dict(),
        "open_order_count": None if open_orders is None else len(open_orders),
        "recovery_check": result.to_dict(),
    }, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
