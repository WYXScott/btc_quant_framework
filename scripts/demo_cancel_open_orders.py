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
    parser = argparse.ArgumentParser(description="Preview or submit cancel-all open orders on Binance Futures Demo/Testnet.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args()

    cfg = load_config()
    if not args.execute:
        guard = ExecutionSafetyGuard.from_config(cfg)
        guard.validate_confirmation(execute=False, confirmation=None)
        result = {
            "status": "preview",
            "dry_run": True,
            "symbol": cfg["symbol"]["ccxt_symbol"],
            "message": "Offline dry-run cancel-all preview only. No exchange request was made.",
        }
    else:
        broker = BinanceFuturesDemoBroker(cfg, require_private=True)
        result = broker.cancel_open_orders(execute=True, confirmation=args.confirm)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
