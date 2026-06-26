from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live.prelive_workflow import PreLiveWorkflowStore


def main() -> None:
    cfg = load_config()
    wf_cfg = cfg.get("prelive_operator_workflow", {})
    expected = str(wf_cfg.get("approval_phrase", "I_REVIEWED_AND_ACCEPT_PRELIVE_RISK"))
    parser = argparse.ArgumentParser(description="Record a manual V2.2 pre-live approval decision.")
    parser.add_argument("--operator", required=True, help="Operator name or initials.")
    parser.add_argument("--decision", default="approve_shadow_only", choices=["approve_shadow_only", "approve_small_live", "reject", "needs_more_demo"], help="Human decision.")
    parser.add_argument("--confirm", required=True, help=f"Required phrase: {expected}")
    parser.add_argument("--notes", default="", help="Decision notes.")
    args = parser.parse_args()
    if args.confirm != expected:
        raise SystemExit(f"Confirmation phrase mismatch. Expected: {expected}")
    db_path = ROOT / cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
    store = PreLiveWorkflowStore(db_path)
    payload = {"expected_phrase": expected, "workflow_version": "v2.2"}
    row = store.append_manual_approval(operator=args.operator, decision=args.decision, confirmation_phrase=args.confirm, notes=args.notes, payload=payload)
    print(json.dumps({"status": "recorded", "approval": row}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
