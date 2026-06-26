from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live import LiveSafetyStore, ShadowLiveReadOnlyClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a read-only live-account shadow snapshot. No orders are ever submitted.")
    parser.add_argument("--fetch-private", action="store_true", help="Actually query private live read-only endpoints using *_READONLY_* env keys.")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    cfg = load_config()
    client = ShadowLiveReadOnlyClient(cfg)
    if args.fetch_private:
        snapshot = client.fetch_private_snapshot()
    else:
        snapshot = client.offline_snapshot()
    out_dir = ROOT / cfg.get("shadow_live", {}).get("output_path", "reports/shadow_live")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = ROOT / args.output if args.output else out_dir / "shadow_live_snapshot.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    try:
        db_path = ROOT / cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
        LiveSafetyStore(db_path).append_shadow_snapshot(snapshot)
    except Exception:
        pass
    print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
    print(f"\nSaved snapshot: {out_path}")


if __name__ == "__main__":
    main()
