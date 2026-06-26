from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.research.sequence_experiments import build_v28_sequence_report


def main() -> None:
    cfg = load_config()
    seq_dir = resolve_path(cfg.get("sequence_models", {}).get("output_path", "reports/sequence_models"))
    wf_dir = resolve_path(cfg.get("sequence_walk_forward", {}).get("output_path", "reports/sequence_walk_forward"))
    out_dir = resolve_path(cfg.get("v2_8_report", {}).get("output_path", "reports/v2_8_sequence_research_report"))
    path = build_v28_sequence_report(seq_dir, wf_dir, out_dir)
    print(f"saved report: {path}")


if __name__ == "__main__":
    main()
