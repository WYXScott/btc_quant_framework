from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from _bootstrap import ROOT  # noqa: E402,F401

from crypto_quant.config import load_config
from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker


def main() -> None:
    cfg = load_config()
    broker = BinanceFuturesDemoBroker(cfg, require_private=True)
    position = broker.fetch_position_snapshot()
    open_orders = broker.fetch_open_orders_snapshot()
    payload = {
        "position": position.to_dict(),
        "open_order_count": len(open_orders),
        "open_orders": open_orders,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
