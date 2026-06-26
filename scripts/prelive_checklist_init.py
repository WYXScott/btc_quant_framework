from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live.prelive_workflow import PreLiveWorkflowStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the V2.2 pre-live manual checklist.")
    parser.add_argument("--reset", action="store_true", help="Reset existing checklist item statuses to pending.")
    args = parser.parse_args()
    cfg = load_config()
    db_path = ROOT / cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
    store = PreLiveWorkflowStore(db_path)
    items = store.initialize_default_checklist(reset=args.reset)
    print(json.dumps({
        "status": "ok",
        "database_path": str(db_path),
        "items": [i.to_dict() for i in items],
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
