from __future__ import annotations

import json
import _bootstrap  # noqa: F401
import pandas as pd

from crypto_quant.config import load_config, resolve_path
from crypto_quant.models.optional_dependencies import optional_dependency_table
from crypto_quant.models.sequence_models import sequence_model_availability_rows


def main() -> None:
    cfg = load_config()
    out_dir = resolve_path(cfg.get("sequence_models", {}).get("output_path", "reports/sequence_models"))
    out_dir.mkdir(parents=True, exist_ok=True)
    availability = pd.DataFrame(sequence_model_availability_rows())
    optional = pd.DataFrame(optional_dependency_table(["torch"]))
    availability.to_csv(out_dir / "sequence_model_availability.csv", index=False, encoding="utf-8-sig")
    optional.to_csv(out_dir / "sequence_optional_dependency_status.csv", index=False, encoding="utf-8-sig")
    payload = {
        "status": "ok",
        "available_models": availability[availability["available"] == True]["model"].tolist(),  # noqa: E712
        "torch_installed": bool(optional.iloc[0]["installed"]) if not optional.empty else False,
    }
    (out_dir / "sequence_backend_availability.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
