from __future__ import annotations

import _bootstrap  # noqa: F401

import numpy as np
import pandas as pd

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns


def main() -> None:
    cfg = load_config()
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    cols = get_model_feature_columns(df)
    rows = []
    for col in cols:
        s = pd.to_numeric(df[col], errors="coerce")
        pos_inf = int(np.isposinf(s.to_numpy()).sum())
        neg_inf = int(np.isneginf(s.to_numpy()).sum())
        nan = int(s.isna().sum())
        max_abs = float(np.nanmax(np.abs(s.replace([np.inf, -np.inf], np.nan)))) if s.notna().any() else float("nan")
        if pos_inf or neg_inf or nan:
            rows.append({"column": col, "+inf": pos_inf, "-inf": neg_inf, "nan": nan, "max_abs_finite": max_abs})
    if not rows:
        print("No NaN or infinite values in model feature columns.")
        return
    out = pd.DataFrame(rows).sort_values(["+inf", "-inf", "nan"], ascending=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
