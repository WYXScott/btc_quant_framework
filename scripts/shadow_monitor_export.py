from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from _bootstrap import ROOT
from crypto_quant.config import load_config


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def main() -> None:
    cfg = load_config()
    db_path = ROOT / cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
    out_dir = ROOT / cfg.get("shadow_monitor", {}).get("output_path", "reports/shadow_monitor")
    out_dir.mkdir(parents=True, exist_ok=True)
    exported: dict[str, str] = {}
    tables = ["shadow_monitor_reports", "shadow_monitor_checks", "shadow_live_snapshots", "target_exposure_decisions", "account_state", "equity_curve"]
    with sqlite3.connect(db_path) as conn:
        for table in tables:
            if _table_exists(conn, table):
                df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
                path = out_dir / f"{table}.csv"
                df.to_csv(path, index=False)
                exported[table] = str(path)
    print(json.dumps({"db_path": str(db_path), "exported": exported}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
