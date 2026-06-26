from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from _bootstrap import ROOT  # noqa: E402,F401

from crypto_quant.config import load_config
from crypto_quant.data.storage import load_parquet
from crypto_quant.exchange import OrderIntent, btc_quantity_from_notional
from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker
from crypto_quant.exchange.safety import ExecutionSafetyGuard


def latest_local_price(cfg: dict) -> float:
    dataset_path = ROOT / cfg["data"]["dataset_path"]
    if dataset_path.exists():
        df = load_parquet(dataset_path)
        if not df.empty:
            return float(df.iloc[-1]["close"])
    raw_path = ROOT / cfg["data"]["raw_path"]
    if raw_path.exists():
        df = load_parquet(raw_path)
        if not df.empty:
            return float(df.iloc[-1]["close"])
    raise FileNotFoundError("No local price data found. Run download_ohlcv.py and build_features.py first, or pass --price.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or submit a tiny Binance Futures Demo/Testnet order.")
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--price", type=float, default=None, help="Reference price. If omitted, use latest local dataset close.")
    parser.add_argument("--notional", type=float, default=None, help="Override order notional in USDT. Still capped by safety config.")
    parser.add_argument("--execute", action="store_true", help="Actually submit to testnet/demo. Default is preview only.")
    parser.add_argument("--confirm", default=None, help="Required confirmation phrase for --execute.")
    parser.add_argument("--reduce-only", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    guard = ExecutionSafetyGuard.from_config(cfg)
    price = float(args.price) if args.price is not None else latest_local_price(cfg)
    leverage = float(cfg["trading"]["leverage"])

    if args.notional is not None:
        qty = float(args.notional) / price
    else:
        qty = btc_quantity_from_notional(
            equity_usdt=float(cfg["trading"]["initial_equity"]),
            reference_price=price,
            margin_fraction=float(cfg["trading"]["max_margin_fraction"]),
            leverage=leverage,
            max_notional_fraction=float(cfg["trading"]["max_notional_fraction"]),
            max_order_notional_usdt=float(guard.cfg.max_order_notional_usdt),
        )

    intent = OrderIntent(
        symbol=str(cfg["symbol"]["ccxt_symbol"]),
        side=args.side,
        order_type="market",
        quantity=qty,
        reduce_only=args.reduce_only,
        leverage=leverage,
        reason="manual_demo_order_preview",
    )
    if not args.execute:
        # Offline dry-run preview: no CCXT import, no credentials, no network.
        intent.validate()
        guard.validate_order_limits(quantity=qty, reference_price=price, leverage=leverage)
        payload = {
            "reference_price": price,
            "estimated_notional_usdt": qty * price,
            "result": {
                "status": "preview",
                "dry_run": True,
                "intent": intent.to_dict(),
                "response": None,
                "message": "Offline dry-run only. No exchange order was sent.",
            },
        }
    else:
        broker = BinanceFuturesDemoBroker(cfg, require_private=True)
        result = broker.place_order(intent, reference_price=price, execute=True, confirmation=args.confirm)
        payload = {
            "reference_price": price,
            "estimated_notional_usdt": qty * price,
            "result": {
                "status": result.status,
                "dry_run": result.dry_run,
                "intent": result.intent,
                "response": result.response,
                "message": result.message,
            },
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
