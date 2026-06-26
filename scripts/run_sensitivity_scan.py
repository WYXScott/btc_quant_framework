from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.models.predict import add_model_probability
from crypto_quant.research.scans import ml_threshold_leverage_scan


def main() -> None:
    cfg = load_config()
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    df = add_model_probability(
        df,
        model_path=resolve_path(cfg["model"]["model_path"]),
        feature_list_path=resolve_path(cfg["model"]["feature_list_path"]),
    )
    scan_cfg = cfg["scan"]
    table = ml_threshold_leverage_scan(
        df=df,
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
        prob_col="prob_up",
        trend_filter=True,
        max_holding_bars=cfg["risk"].get("max_holding_bars"),
    )
    out_dir = resolve_path("reports/sensitivity_scan")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ml_threshold_leverage_scan.csv"
    table.to_csv(out_path, index=False, encoding="utf-8-sig")
    top = table.head(10).to_dict(orient="records") if not table.empty else []
    print(json.dumps(top, ensure_ascii=False, indent=2))
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
