from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.models.walk_forward import WalkForwardConfig, walk_forward_predict
from crypto_quant.research.scans import ml_threshold_leverage_scan


def main() -> None:
    cfg = load_config()
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(df)
    wf_cfg = WalkForwardConfig(
        train_window_days=cfg["walk_forward"]["train_window_days"],
        test_window_days=cfg["walk_forward"]["test_window_days"],
        min_train_bars=cfg["walk_forward"]["min_train_bars"],
        start=cfg["walk_forward"].get("start"),
        end=cfg["walk_forward"].get("end"),
    )
    pred_df, folds = walk_forward_predict(df, feature_columns, wf_cfg, probability_col="prob_up_wf")
    scan_cfg = cfg["scan"]
    table = ml_threshold_leverage_scan(
        df=pred_df,
        leverages=scan_cfg["leverages"],
        buy_thresholds=scan_cfg["buy_thresholds"],
        exit_thresholds=scan_cfg["exit_thresholds"],
        timeframe=cfg["data"]["timeframe"],
        initial_equity=cfg["trading"]["initial_equity"],
        max_margin_fraction=cfg["trading"]["max_margin_fraction"],
        max_notional_fraction=cfg["trading"]["max_notional_fraction"],
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
        prob_col="prob_up_wf",
        trend_filter=True,
        max_holding_bars=cfg["risk"].get("max_holding_bars"),
    )
    out_dir = resolve_path("reports/walk_forward_scan")
    out_dir.mkdir(parents=True, exist_ok=True)
    folds.to_csv(out_dir / "walk_forward_folds.csv", index=False, encoding="utf-8-sig")
    table.to_csv(out_dir / "walk_forward_threshold_leverage_scan.csv", index=False, encoding="utf-8-sig")
    top = table.head(10).to_dict(orient="records") if not table.empty else []
    print(json.dumps(top, ensure_ascii=False, indent=2))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
