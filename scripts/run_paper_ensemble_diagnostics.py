from __future__ import annotations

import _bootstrap  # noqa: F401

import pandas as pd

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.database import PaperStore
from crypto_quant.backtest.metrics import drawdown_series


def main() -> None:
    cfg = load_config()
    out_dir = resolve_path(cfg.get("ensemble_paper", {}).get("output_path", "reports/ensemble_paper"))
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = resolve_path(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    store = PaperStore(db_path)
    decisions = store.read_table("target_exposure_decisions")
    equity = store.read_table("equity_curve")
    orders = store.read_table("orders")
    summary = {
        "num_decisions": int(len(decisions)),
        "num_orders": int(len(orders)),
        "num_rebalances": int((decisions.get("action", pd.Series(dtype=str)).isin(["increase", "reduce", "close"])).sum()) if not decisions.empty else 0,
        "latest_equity": None,
        "latest_position_qty": None,
        "latest_target_exposure": None,
        "latest_current_exposure": None,
        "paper_max_drawdown": None,
    }
    if not equity.empty:
        eq = pd.to_numeric(equity["equity"], errors="coerce").dropna()
        if not eq.empty:
            summary["latest_equity"] = float(eq.iloc[-1])
            summary["paper_max_drawdown"] = float(drawdown_series(eq).min())
        summary["latest_position_qty"] = float(pd.to_numeric(equity["position_qty"], errors="coerce").fillna(0).iloc[-1])
    if not decisions.empty:
        summary["latest_target_exposure"] = float(pd.to_numeric(decisions["target_exposure"], errors="coerce").fillna(0).iloc[-1])
        summary["latest_current_exposure"] = float(pd.to_numeric(decisions["current_exposure_after"], errors="coerce").fillna(0).iloc[-1])
    pd.DataFrame([summary]).to_csv(out_dir / "ensemble_paper_summary.csv", index=False, encoding="utf-8-sig")
    decisions.to_csv(out_dir / "ensemble_paper_decisions.csv", index=False, encoding="utf-8-sig")
    orders.to_csv(out_dir / "ensemble_paper_orders.csv", index=False, encoding="utf-8-sig")
    equity.to_csv(out_dir / "ensemble_paper_equity_curve.csv", index=False, encoding="utf-8-sig")
    print("ensemble paper summary:")
    print(summary)
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
