from __future__ import annotations

import json
import _bootstrap  # noqa: F401

import matplotlib.pyplot as plt

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.research.model_diagnostics import train_validation_diagnostics


def main() -> None:
    cfg = load_config()
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(df)
    out_dir = resolve_path("reports/model_diagnostics")
    out_dir.mkdir(parents=True, exist_ok=True)

    diag = train_validation_diagnostics(
        dataset=df,
        feature_columns=feature_columns,
        train_end=cfg["model"]["train_end"],
        valid_end=cfg["model"]["valid_end"],
    )

    (out_dir / "model_metrics.json").write_text(json.dumps(diag.metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    diag.threshold_table.to_csv(out_dir / "threshold_diagnostics.csv", index=False, encoding="utf-8-sig")
    diag.feature_importance.to_csv(out_dir / "feature_importance.csv", index=False, encoding="utf-8-sig")
    diag.calibration_table.to_csv(out_dir / "calibration_table.csv", index=False, encoding="utf-8-sig")
    diag.predictions.to_csv(out_dir / "diagnostic_predictions.csv", encoding="utf-8-sig")

    top = diag.feature_importance.head(20).iloc[::-1]
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(111)
    ax.barh(top["feature"], top["importance"])
    ax.set_title("Top 20 Feature Importances")
    ax.set_xlabel("Importance")
    fig.tight_layout()
    fig.savefig(out_dir / "feature_importance_top20.png", dpi=200)
    plt.close(fig)

    if not diag.calibration_table.empty and {"prob_mean", "actual_positive_rate"}.issubset(diag.calibration_table.columns):
        fig = plt.figure(figsize=(6, 5))
        ax = fig.add_subplot(111)
        ax.plot([0, 1], [0, 1], linestyle="--")
        ax.scatter(diag.calibration_table["prob_mean"], diag.calibration_table["actual_positive_rate"])
        ax.set_title("Probability Calibration")
        ax.set_xlabel("Mean predicted probability")
        ax.set_ylabel("Actual positive rate")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(out_dir / "calibration_curve.png", dpi=200)
        plt.close(fig)

    print(json.dumps(diag.metrics, indent=2, ensure_ascii=False))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
