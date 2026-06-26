from __future__ import annotations

import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live import KillSwitch, LiveSafetyGate, PreLiveValidationBuilder, ShadowLiveReadOnlyClient


def main() -> None:
    cfg = load_config()
    prelive = PreLiveValidationBuilder(cfg, root=ROOT).build()
    gate = LiveSafetyGate(cfg, root=ROOT).evaluate(mode="readiness_report").to_dict()
    shadow = ShadowLiveReadOnlyClient(cfg).offline_snapshot()
    kill = KillSwitch(ROOT / cfg.get("live_trading", {}).get("kill_switch_path", "data/database/KILL_SWITCH.json")).status()
    report = {
        "timestamp_utc": gate["timestamp_utc"],
        "overall_status": "blocked" if gate["status"] == "blocked" or prelive["status"] != "pass" or kill.get("enabled") else "pass",
        "live_gate": gate,
        "prelive_validation": prelive,
        "kill_switch": kill,
        "shadow_live_offline_preview": shadow,
        "note": "V2.0 is designed to block real trading by default. Use shadow live only with read-only API keys.",
    }
    out = ROOT / "reports/live_safety/v2_live_readiness_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\nSaved V2.0 readiness report: {out}")


if __name__ == "__main__":
    main()
