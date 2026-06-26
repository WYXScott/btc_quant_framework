from __future__ import annotations

import argparse
import json
import sqlite3

import pandas as pd

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live import HardCircuitBreaker, LiveSafetyStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate hard drawdown/daily-loss circuit breakers from local equity curve.")
    parser.add_argument("--output", default="reports/live_safety/hard_circuit_report.json")
    args = parser.parse_args()

    cfg = load_config()
    db_path = ROOT / cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                df = pd.read_sql_query("SELECT * FROM equity_curve ORDER BY timestamp", conn)
        except Exception:
            df = pd.DataFrame()
    else:
        df = pd.DataFrame()
    live_cfg = cfg.get("live_trading", {})
    report = HardCircuitBreaker(
        max_daily_loss_fraction=float(live_cfg.get("max_daily_loss_fraction", 0.02)),
        max_total_drawdown_fraction=float(live_cfg.get("max_total_drawdown_fraction", 0.10)),
    ).evaluate_equity_curve(df)
    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    try:
        LiveSafetyStore(db_path).append_event("hard_circuit_check", report.status, report.message, report.to_dict())
    except Exception:
        pass
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
