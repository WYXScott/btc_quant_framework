from __future__ import annotations

from _bootstrap import ROOT

from crypto_quant.config import load_config
from crypto_quant.research.model_admission import run_model_strategy_admission


def main() -> None:
    cfg = load_config()
    summary = run_model_strategy_admission(cfg)
    out_dir = ROOT / cfg.get("model_admission", {}).get("output_path", "reports/model_admission")
    print("V2.9 unified model/strategy admission completed")
    print(f"Output: {out_dir}")
    print(summary)


if __name__ == "__main__":
    main()
