from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from _bootstrap import ROOT  # noqa: E402,F401

from crypto_quant.config import load_config
from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker
from crypto_quant.exchange.safety import ExecutionSafetyGuard


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or submit leverage update to Binance Futures Demo/Testnet.")
    parser.add_argument("--leverage", type=float, default=None)
    parser.add_argument("--execute", action="store_true", help="Actually submit leverage update. Default is preview only.")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args()

    cfg = load_config()
    leverage = float(args.leverage if args.leverage is not None else cfg["trading"]["leverage"])
    if not args.execute:
        guard = ExecutionSafetyGuard.from_config(cfg)
        guard.validate_order_limits(quantity=1e-8, reference_price=1.0, leverage=leverage)
        result = {
            "status": "preview",
            "dry_run": True,
            "symbol": cfg["symbol"]["ccxt_symbol"],
            "leverage": leverage,
            "message": "Offline dry-run leverage update preview only. No network request was made.",
        }
    else:
        broker = BinanceFuturesDemoBroker(cfg, require_private=True)
        result = broker.set_leverage(leverage, execute=True, confirmation=args.confirm)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
