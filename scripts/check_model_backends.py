from __future__ import annotations

import json
import _bootstrap  # noqa: F401
import pandas as pd

from crypto_quant.config import resolve_path
from crypto_quant.models.registry import model_availability_rows, available_models
from crypto_quant.models.optional_dependencies import optional_dependency_table


def main() -> None:
    out_dir = resolve_path("reports/model_backends")
    out_dir.mkdir(parents=True, exist_ok=True)
    model_rows = model_availability_rows()
    dep_rows = optional_dependency_table()
    pd.DataFrame(model_rows).to_csv(out_dir / "model_backend_availability.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(dep_rows).to_csv(out_dir / "optional_dependency_status.csv", index=False, encoding="utf-8-sig")
    payload = {
        "available_models": available_models(include_unavailable=False),
        "all_models": available_models(include_unavailable=True),
        "models": model_rows,
        "optional_dependencies": dep_rows,
    }
    (out_dir / "model_backend_availability.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
