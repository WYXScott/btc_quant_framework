from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.research.signal_confidence import run_signal_confidence_analysis


def main() -> None:
    cfg = load_config()
    calibration_cfg = cfg.get("calibration", {})
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    payload = run_signal_confidence_analysis(
        dataset=df,
        calibrated_model_path=resolve_path(calibration_cfg.get("calibrated_model_path", "models/btc_direction_model_calibrated.joblib")),
        output_dir=resolve_path(calibration_cfg.get("confidence_output_path", "reports/signal_confidence")),
        cfg=cfg,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
