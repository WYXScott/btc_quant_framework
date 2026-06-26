from __future__ import annotations

from _bootstrap import ROOT

from crypto_quant.config import load_config, resolve_path
from crypto_quant.ops.daily_report import build_signal_hit_rate, _ops_cfg


def main() -> None:
    cfg = load_config()
    ocfg = _ops_cfg(cfg)
    out_dir = resolve_path(ocfg.output_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary, pred, tier_hit = build_signal_hit_rate(cfg)
    (out_dir / "signal_hit_rate_summary.json").write_text(__import__("json").dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    if not tier_hit.empty:
        tier_hit.to_csv(out_dir / "signal_hit_rate_by_tier.csv", index=False)
    if not pred.empty:
        pred.tail(int(ocfg.max_table_rows)).to_csv(out_dir / "signal_hit_rate_prediction_tail.csv", index=False)
    print("Signal hit-rate report completed")
    print(f"Output: {out_dir}")
    print(summary)


if __name__ == "__main__":
    main()
