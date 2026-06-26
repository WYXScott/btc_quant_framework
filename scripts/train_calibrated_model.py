from __future__ import annotations

import json
import _bootstrap  # noqa: F401

import matplotlib.pyplot as plt
import pandas as pd

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.models.calibration import train_calibrated_direction_model


def main() -> None:
    cfg = load_config()
    calibration_cfg = cfg.get("calibration", {})
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(df)
    out_dir = resolve_path(calibration_cfg.get("output_path", "reports/calibration"))
    out_dir.mkdir(parents=True, exist_ok=True)

    result = train_calibrated_direction_model(
        dataset=df,
        feature_columns=feature_columns,
        train_end=cfg["model"]["train_end"],
        valid_end=cfg["model"]["valid_end"],
        model_path=resolve_path(calibration_cfg.get("calibrated_model_path", "models/btc_direction_model_calibrated.joblib")),
        feature_list_path=resolve_path(calibration_cfg.get("feature_list_path", cfg["model"]["feature_list_path"])),
        model_type=cfg.get("model", {}).get("type", "extra_trees_classifier"),
        calibration_method=calibration_cfg.get("method", "isotonic"),
        bins=int(calibration_cfg.get("bins", 10)),
    )

    metrics = result["metrics"]
    (out_dir / "calibration_metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    result["reliability_raw"].to_csv(out_dir / "reliability_raw.csv", index=False, encoding="utf-8-sig")
    result["reliability_calibrated"].to_csv(out_dir / "reliability_calibrated.csv", index=False, encoding="utf-8-sig")
    result["predictions"].to_csv(out_dir / "calibrated_predictions.csv", encoding="utf-8-sig")

    # Comparison table for convenience.
    rows = []
    for section in ["raw", "calibrated"]:
        row = {"probability_version": section}
        row.update(metrics[section])
        rows.append(row)
    pd.DataFrame(rows).to_csv(out_dir / "raw_vs_calibrated_metrics.csv", index=False, encoding="utf-8-sig")

    fig = plt.figure(figsize=(7, 6))
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1], linestyle="--", label="perfect")
    raw = result["reliability_raw"]
    cal = result["reliability_calibrated"]
    if not raw.empty:
        ax.plot(raw["prob_mean"], raw["actual_positive_rate"], marker="o", label="raw")
    if not cal.empty:
        ax.plot(cal["prob_mean"], cal["actual_positive_rate"], marker="o", label="calibrated")
    ax.set_title("Raw vs Calibrated Reliability")
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Actual positive rate")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "raw_vs_calibrated_reliability.png", dpi=200)
    plt.close(fig)

    html_metrics = pd.DataFrame(rows).to_html(index=False, border=0, classes="table")
    html_rel = cal.to_html(index=False, border=0, classes="table") if not cal.empty else "<p>No calibrated reliability table.</p>"
    html = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>BTC Probability Calibration</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;margin:32px;background:#f7f8fb;color:#111827;}}
.card{{background:white;border-radius:18px;padding:22px;margin-bottom:18px;box-shadow:0 10px 28px rgba(15,23,42,.08);}}
.table{{border-collapse:collapse;width:100%;}} .table th,.table td{{border-bottom:1px solid #e5e7eb;padding:8px;text-align:left;}}
.table th{{background:#111827;color:white;}} img{{max-width:100%;border-radius:12px;border:1px solid #e5e7eb;}}
</style></head><body>
<div class='card'><h1>BTC V2.5 概率校准报告</h1><p>校准方法：{calibration_cfg.get('method', 'isotonic')}。Brier/ECE 越低越好；ROC-AUC 主要衡量排序能力。</p></div>
<div class='card'><h2>Raw vs Calibrated</h2>{html_metrics}</div>
<div class='card'><h2>Reliability Curve</h2><img src='raw_vs_calibrated_reliability.png'></div>
<div class='card'><h2>Calibrated Bucket Table</h2>{html_rel}</div>
</body></html>"""
    (out_dir / "calibration_report.html").write_text(html, encoding="utf-8")

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
