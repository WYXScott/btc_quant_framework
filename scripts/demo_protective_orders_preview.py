from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from _bootstrap import ROOT  # noqa: E402,F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker
from crypto_quant.exchange.position_sizing import btc_quantity_from_notional
from crypto_quant.exchange.protective_orders import (
    build_long_protective_order_plan,
    protective_levels_from_percentages,
)
from crypto_quant.exchange.safety import ExecutionSafetyGuard
from crypto_quant.paper.database import PaperStore


def latest_dataset_row(cfg: dict):
    dataset_path = resolve_path(cfg["data"]["dataset_path"])
    if dataset_path.exists():
        df = load_parquet(dataset_path)
        if not df.empty:
            return df.iloc[-1]
    raw_path = resolve_path(cfg["data"]["raw_path"])
    if raw_path.exists():
        df = load_parquet(raw_path)
        if not df.empty:
            return df.iloc[-1]
    return None


def infer_levels(cfg: dict, *, entry_price: float, row, stop_price: float | None, take_profit_price: float | None):
    if stop_price is not None and take_profit_price is not None:
        return float(stop_price), float(take_profit_price), "explicit_cli"

    native_cfg = cfg.get("native_protection", {})
    atr_window = int(cfg.get("features", {}).get("atr_window", 14))
    atr_col = f"atr_{atr_window}"
    atr = None if row is None or atr_col not in row.index else row.get(atr_col)
    if atr is not None and float(atr) > 0:
        sl = entry_price - float(atr) * float(cfg["risk"].get("stop_loss_atr_multiple", 2.5))
        tp = entry_price + float(atr) * float(cfg["risk"].get("take_profit_atr_multiple", 4.0))
        return float(stop_price if stop_price is not None else sl), float(take_profit_price if take_profit_price is not None else tp), f"atr:{atr_col}"

    sl, tp = protective_levels_from_percentages(
        entry_price=entry_price,
        stop_loss_pct=float(native_cfg.get("fallback_stop_loss_pct", 0.02)),
        take_profit_pct=float(native_cfg.get("fallback_take_profit_pct", 0.04)),
    )
    return float(stop_price if stop_price is not None else sl), float(take_profit_price if take_profit_price is not None else tp), "fallback_percentages"


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or submit Binance Futures Demo/Testnet native protective orders.")
    parser.add_argument("--entry-price", type=float, default=None)
    parser.add_argument("--qty", type=float, default=None, help="BTC quantity. If omitted, use local paper position, then safety-capped notional.")
    parser.add_argument("--stop-price", type=float, default=None)
    parser.add_argument("--take-profit-price", type=float, default=None)
    parser.add_argument("--enable-trailing-stop", action="store_true")
    parser.add_argument("--trailing-activation-price", type=float, default=None)
    parser.add_argument("--trailing-callback-rate", type=float, default=None)
    parser.add_argument("--execute", action="store_true", help="Submit protective orders to Demo/Testnet. Default is offline preview.")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args()

    cfg = load_config()
    native_cfg = cfg.get("native_protection", {})
    row = latest_dataset_row(cfg)
    guard = ExecutionSafetyGuard.from_config(cfg)
    store = PaperStore(resolve_path(cfg["paper"]["database_path"]))
    account = store.load_account(
        initial_equity=float(cfg["trading"]["initial_equity"]),
        leverage=float(cfg["trading"]["leverage"]),
    )

    latest_close = None if row is None else float(row["close"])
    entry_price = float(args.entry_price or account.entry_price or latest_close or 0.0)
    if entry_price <= 0:
        raise ValueError("Cannot infer entry price. Pass --entry-price or build local market data first.")

    if args.qty is not None:
        qty = float(args.qty)
    elif account.in_position:
        qty = abs(float(account.position_qty))
    else:
        qty = btc_quantity_from_notional(
            equity_usdt=float(cfg["trading"]["initial_equity"]),
            reference_price=entry_price,
            margin_fraction=float(cfg["trading"]["max_margin_fraction"]),
            leverage=float(cfg["trading"]["leverage"]),
            max_notional_fraction=float(cfg["trading"]["max_notional_fraction"]),
            max_order_notional_usdt=float(guard.cfg.max_order_notional_usdt),
        )

    stop_price, take_profit_price, level_source = infer_levels(
        cfg,
        entry_price=entry_price,
        row=row,
        stop_price=args.stop_price,
        take_profit_price=args.take_profit_price,
    )

    trailing_enabled = bool(args.enable_trailing_stop or native_cfg.get("enable_trailing_stop", False))
    activation = args.trailing_activation_price
    if activation is None and trailing_enabled:
        activation = entry_price * (1.0 + float(native_cfg.get("trailing_activation_pct", 0.01)))
    callback_rate = args.trailing_callback_rate
    if callback_rate is None:
        callback_rate = native_cfg.get("trailing_callback_rate")

    plan = build_long_protective_order_plan(
        symbol=str(cfg["symbol"]["ccxt_symbol"]),
        quantity=qty,
        entry_price=entry_price,
        stop_loss_price=stop_price,
        take_profit_price=take_profit_price,
        trailing_activation_price=activation,
        trailing_callback_rate=None if callback_rate is None else float(callback_rate),
        leverage=float(cfg["trading"]["leverage"]),
        working_type=native_cfg.get("working_type", "MARK_PRICE"),
        position_side=native_cfg.get("position_side", "BOTH"),
        enable_stop_loss=bool(native_cfg.get("enable_stop_loss", True)),
        enable_take_profit=bool(native_cfg.get("enable_take_profit", True)),
        enable_trailing_stop=trailing_enabled,
    )

    payload = {
        "mode": "execute" if args.execute else "offline_preview",
        "level_source": level_source,
        "estimated_position_notional_usdt": qty * entry_price,
        "plan": plan.to_dict(),
        "result": {
            "status": "preview",
            "dry_run": True,
            "message": "Offline preview only. No exchange order was sent.",
        },
    }

    if args.execute:
        broker = BinanceFuturesDemoBroker(cfg, require_private=True)
        payload["result"] = broker.place_protective_order_plan(
            plan,
            execute=True,
            confirmation=args.confirm,
        )

    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
