from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.models.walk_forward import WalkForwardConfig, walk_forward_predict
from crypto_quant.strategy.ml_strategy import probability_signal
from crypto_quant.backtest.engine import LeveragedBacktester
from crypto_quant.research.strategy_diagnostics import leverage_risk_table


def main() -> None:
    cfg = load_config()
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(df)
    wf_cfg = WalkForwardConfig.from_config(cfg)
    pred_df, _ = walk_forward_predict(df, feature_columns, wf_cfg, probability_col="prob_up_wf")
    signal_df = probability_signal(
        pred_df,
        prob_col="prob_up_wf",
        buy_threshold=cfg["model"]["probability_buy_threshold"],
        exit_threshold=cfg["model"]["probability_exit_threshold"],
        trend_filter=True,
        max_holding_bars=cfg["risk"].get("max_holding_bars"),
    )
    base_bt = LeveragedBacktester(
        initial_equity=cfg["trading"]["initial_equity"],
        leverage=cfg["trading"]["leverage"],
        max_margin_fraction=cfg["trading"]["max_margin_fraction"],
        max_notional_fraction=cfg["trading"]["max_notional_fraction"],
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
    )
    base_result = base_bt.run(signal_df, signal_col="signal")
    table = leverage_risk_table(
        base_result,
        timeframe=cfg["data"]["timeframe"],
        leverages=cfg["scan"].get("leverages", [1, 2, 3, 5, 10]),
        max_margin_fraction=cfg["trading"]["max_margin_fraction"],
        max_notional_fraction=cfg["trading"]["max_notional_fraction"],
    )
    out_dir = resolve_path("reports/leverage_risk")
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / "leverage_risk_table.csv", index=False, encoding="utf-8-sig")
    print(json.dumps(table.to_dict(orient="records"), indent=2, ensure_ascii=False))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
