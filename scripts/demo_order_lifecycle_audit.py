from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.database import PaperStore


def summarize(store: PaperStore) -> dict:
    out: dict = {}
    for table in ["exchange_order_lifecycle", "order_state_transitions", "protection_recalc_plans", "cancel_failure_events"]:
        df = store.read_table(table)
        out[table] = {
            "rows": int(len(df)),
            "columns": list(df.columns),
        }
        if not df.empty:
            out[table]["tail"] = df.tail(5).to_dict(orient="records")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Print V1.9 order lifecycle audit table summaries.")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()
    cfg = load_config()
    store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
    print(json.dumps(summarize(store), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
