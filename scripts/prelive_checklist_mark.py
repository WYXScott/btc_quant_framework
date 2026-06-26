from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live.prelive_workflow import PreLiveWorkflowStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark one V2.2 pre-live checklist item.")
    parser.add_argument("item_key", help="Checklist item key. Run prelive_checklist_init.py to list keys.")
    parser.add_argument("status", choices=["pending", "approved", "waived", "failed", "pass", "warn", "blocked"], help="New item status.")
    parser.add_argument("--operator", default="operator", help="Operator name or initials.")
    parser.add_argument("--evidence", default="", help="Path or note pointing to supporting evidence.")
    parser.add_argument("--notes", default="", help="Free-form notes.")
    args = parser.parse_args()
    cfg = load_config()
    db_path = ROOT / cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
    store = PreLiveWorkflowStore(db_path)
    store.initialize_default_checklist(reset=False)
    item = store.mark_item(args.item_key, args.status, operator=args.operator, evidence_path=args.evidence, notes=args.notes)
    print(json.dumps({"status": "ok", "item": item.to_dict()}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
