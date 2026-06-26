from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live import LiveSafetyStore, PreLiveValidationBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the V2.0 pre-live validation report.")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    cfg = load_config()
    report = PreLiveValidationBuilder(cfg, root=ROOT).build()
    out_path = ROOT / (args.output or cfg.get("live_trading", {}).get(
        "prelive_validation_report_path", "reports/prelive_validation/prelive_validation_report.json"
    ))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    try:
        db_path = ROOT / cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
        LiveSafetyStore(db_path).append_prelive_report(report, report_path=out_path)
    except Exception:
        pass
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\nSaved pre-live validation report: {out_path}")


if __name__ == "__main__":
    main()
