from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from _bootstrap import ROOT

from crypto_quant.config import load_config
from crypto_quant.ops.daily_report import build_v30_operations_report
from crypto_quant.paper.database import PaperStore
from crypto_quant.paper.account import PaperAccount


def main() -> None:
    cfg = load_config()
    cfg = dict(cfg)
    cfg["operations"] = dict(cfg.get("operations", {}))
    cfg["operations"]["output_path"] = "reports/operations_smoke"
    cfg["operations"]["paper_db_path"] = "data/database/smoke_operations.sqlite"
    cfg["operations"]["admission_leaderboard_path"] = "reports/model_admission_smoke/model_strategy_leaderboard.csv"
    cfg["operations"]["confidence_dataset_path"] = "reports/walk_forward_calibration_smoke/walk_forward_confidence_dataset.csv"
    cfg["v3_0_report"] = {"output_path": "reports/v3_0_operations_smoke"}

    db = ROOT / cfg["operations"]["paper_db_path"]
    if db.exists():
        db.unlink()
    store = PaperStore(db)
    account = PaperAccount(equity=1000, cash=1000, leverage=3)
    store.save_account(account)
    with store.connect() as conn:
        base = pd.Timestamp("2026-01-01", tz="UTC")
        for i in range(20):
            price = 50000 + 100 * i
            equity = 1000 + 2 * i - max(i - 12, 0) * 5
            conn.execute(
                """
                INSERT OR REPLACE INTO equity_curve(timestamp, price, cash, equity, position_qty, entry_price, leverage, realized_pnl, unrealized_pnl, bars_held)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(base + pd.Timedelta(hours=4*i)), price, 1000, equity, 0.01 if i > 3 else 0.0, 50000, 3, i, 0, i),
            )
        conn.execute(
            """
            INSERT INTO orders(timestamp, side, price, qty, notional, fee, pnl, status, reason, equity_after)
            VALUES (?, 'buy', 50100, 0.01, 501, 0.5, 0, 'filled', 'smoke', 1002)
            """,
            (str(base + pd.Timedelta(hours=16)),),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO target_exposure_decisions(timestamp, price, ensemble_score, signal, target_exposure, target_notional, action, reason, equity, cash, position_qty)
            VALUES (?, 50200, 0.7, 1, 1.5, 1500, 'increase', 'smoke', 1005, 1000, 0.01)
            """,
            (str(base + pd.Timedelta(hours=20)),),
        )
    payload = build_v30_operations_report(cfg)
    out = ROOT / "reports/operations_smoke/operations_smoke_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    assert (ROOT / "reports/v3_0_operations_smoke/v3_0_operations_report.html").exists()
    print("operations_smoke passed")


if __name__ == "__main__":
    main()
