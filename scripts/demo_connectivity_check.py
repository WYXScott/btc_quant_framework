from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from _bootstrap import ROOT  # noqa: E402,F401

from crypto_quant.config import load_config
from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Binance Futures Demo/Testnet adapter.")
    parser.add_argument("--online", action="store_true", help="Perform public network calls: fetch time/markets/ticker.")
    parser.add_argument("--private", action="store_true", help="Also test private balance endpoint. Requires testnet keys.")
    args = parser.parse_args()

    cfg = load_config()
    broker = BinanceFuturesDemoBroker(cfg, require_private=args.private)
    print(json.dumps({"config": broker.describe()}, indent=2, ensure_ascii=False))

    if args.online:
        public = broker.public_connectivity_check()
        print(json.dumps({"public_check": public}, indent=2, ensure_ascii=False))
    else:
        print("Public online check skipped. Add --online to test public connectivity.")

    if args.private:
        private = broker.private_connectivity_check()
        print(json.dumps({"private_check": private}, indent=2, ensure_ascii=False))
    else:
        print("Private online check skipped. Add --private with testnet keys to test account access.")


if __name__ == "__main__":
    main()
