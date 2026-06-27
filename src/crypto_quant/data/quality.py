from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import json
import numpy as np
import pandas as pd


@dataclass
class QualityIssue:
    severity: str
    category: str
    message: str
    count: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    sample: str | None = None


def timeframe_to_timedelta(timeframe: str) -> pd.Timedelta:
    unit = timeframe[-1].lower()
    value = int(timeframe[:-1])
    if unit == "m":
        return pd.Timedelta(minutes=value)
    if unit == "h":
        return pd.Timedelta(hours=value)
    if unit == "d":
        return pd.Timedelta(days=value)
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _ts(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(pd.Timestamp(value))


def _issue_from_mask(
    df: pd.DataFrame,
    mask: pd.Series,
    severity: str,
    category: str,
    message: str,
    sample_cols: list[str] | None = None,
) -> QualityIssue | None:
    mask = mask.fillna(False)
    count = int(mask.sum())
    if count == 0:
        return None
    bad = df.loc[mask]
    sample = None
    if sample_cols:
        cols = [c for c in sample_cols if c in bad.columns]
        if cols:
            sample = bad[cols].head(5).to_json(orient="index", date_format="iso")
    return QualityIssue(
        severity=severity,
        category=category,
        message=message,
        count=count,
        first_timestamp=_ts(bad.index.min()),
        last_timestamp=_ts(bad.index.max()),
        sample=sample,
    )


def run_ohlcv_quality_checks(
    df: pd.DataFrame,
    timeframe: str = "4h",
    *,
    max_abs_log_return: float = 0.20,
    zscore_threshold: float = 8.0,
    max_range_pct: float = 0.35,
    max_zero_volume_fraction: float = 0.01,
    allow_incomplete_latest_bar: bool = True,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Validate OHLCV candles before feature/model generation.

    The function is intentionally conservative: it does not mutate or fill data. It only reports
    problems so the user can decide whether to rebuild, patch or exclude a period.
    """
    issues: list[QualityIssue] = []
    required = ["open", "high", "low", "close", "volume"]
    data = df.copy()

    missing_cols = [c for c in required if c not in data.columns]
    if missing_cols:
        issues.append(QualityIssue("critical", "schema", f"Missing required OHLCV columns: {missing_cols}", len(missing_cols)))
        report = _build_report(data, timeframe, issues, expected_bars=None)
        return report, pd.DataFrame([asdict(i) for i in issues])

    if data.empty:
        issues.append(QualityIssue("critical", "empty", "OHLCV dataframe is empty", 0))
        report = _build_report(data, timeframe, issues, expected_bars=0)
        return report, pd.DataFrame([asdict(i) for i in issues])

    if not isinstance(data.index, pd.DatetimeIndex):
        issues.append(QualityIssue("critical", "index", "Index is not a DatetimeIndex", len(data)))
        data.index = pd.to_datetime(data.index, utc=True, errors="coerce")
    elif data.index.tz is None:
        issues.append(QualityIssue("warning", "timezone", "DatetimeIndex has no timezone; assuming UTC for checks", len(data)))
        data.index = data.index.tz_localize("UTC")
    else:
        data.index = data.index.tz_convert("UTC")

    duplicate_mask = data.index.duplicated(keep=False)
    if duplicate_mask.any():
        dup_idx = data.index[duplicate_mask]
        issues.append(QualityIssue("critical", "duplicate_timestamp", "Duplicate candle timestamps detected", int(duplicate_mask.sum()), _ts(dup_idx.min()), _ts(dup_idx.max())))

    if not data.index.is_monotonic_increasing:
        issues.append(QualityIssue("warning", "index_order", "Index is not sorted ascending", len(data)))
        data = data.sort_index()

    expected_delta = timeframe_to_timedelta(timeframe)
    full_index = pd.date_range(data.index.min(), data.index.max(), freq=expected_delta, tz="UTC")
    missing_index = full_index.difference(data.index.unique())
    if allow_incomplete_latest_bar and len(missing_index) > 0:
        # Keep all historical gaps; the latest expected bar might be incomplete and therefore absent.
        latest_expected = full_index.max()
        missing_index = missing_index[missing_index != latest_expected]
    if len(missing_index) > 0:
        issues.append(QualityIssue("critical", "missing_candles", "Missing expected candles in OHLCV time series", int(len(missing_index)), _ts(missing_index.min()), _ts(missing_index.max()), sample=str(list(map(str, missing_index[:10])))))

    numeric = data[required].apply(pd.to_numeric, errors="coerce")
    nan_mask = numeric.isna().any(axis=1)
    issue = _issue_from_mask(data.assign(**numeric), nan_mask, "critical", "nan_values", "NaN/non-numeric values found in OHLCV columns", required)
    if issue:
        issues.append(issue)

    inf_mask = ~np.isfinite(numeric).all(axis=1)
    issue = _issue_from_mask(data.assign(**numeric), pd.Series(inf_mask, index=data.index), "critical", "infinite_values", "Infinite values found in OHLCV columns", required)
    if issue:
        issues.append(issue)

    non_positive_price = (numeric[["open", "high", "low", "close"]] <= 0).any(axis=1)
    issue = _issue_from_mask(data.assign(**numeric), non_positive_price, "critical", "non_positive_price", "Open/high/low/close must be positive", required)
    if issue:
        issues.append(issue)

    negative_volume = numeric["volume"] < 0
    issue = _issue_from_mask(data.assign(**numeric), negative_volume, "critical", "negative_volume", "Volume must not be negative", required)
    if issue:
        issues.append(issue)

    zero_volume = numeric["volume"] == 0
    zero_fraction = float(zero_volume.mean()) if len(zero_volume) else 0.0
    if zero_fraction > max_zero_volume_fraction:
        issue = _issue_from_mask(data.assign(**numeric), zero_volume, "warning", "zero_volume", f"Zero-volume candles exceed threshold {max_zero_volume_fraction:.2%}", required)
        if issue:
            issues.append(issue)

    ohlc_inconsistent = (numeric["high"] < numeric[["open", "close", "low"]].max(axis=1)) | (numeric["low"] > numeric[["open", "close", "high"]].min(axis=1))
    issue = _issue_from_mask(data.assign(**numeric), ohlc_inconsistent, "critical", "ohlc_consistency", "OHLC values violate high/low envelope", required)
    if issue:
        issues.append(issue)

    log_ret = np.log(numeric["close"]).diff()
    extreme_abs = log_ret.abs() > max_abs_log_return
    issue = _issue_from_mask(data.assign(log_ret=log_ret, **numeric), extreme_abs, "warning", "extreme_return_abs", f"Absolute log return exceeds {max_abs_log_return:.2%}", ["open", "high", "low", "close", "log_ret"])
    if issue:
        issues.append(issue)

    rolling_med = log_ret.rolling(120, min_periods=30).median()
    rolling_mad = (log_ret - rolling_med).abs().rolling(120, min_periods=30).median()
    robust_z = 0.6745 * (log_ret - rolling_med) / rolling_mad.replace(0, np.nan)
    extreme_z = robust_z.abs() > zscore_threshold
    issue = _issue_from_mask(data.assign(log_ret=log_ret, robust_z=robust_z, **numeric), extreme_z, "warning", "extreme_return_zscore", f"Robust return z-score exceeds {zscore_threshold}", ["close", "log_ret", "robust_z"])
    if issue:
        issues.append(issue)

    range_pct = (numeric["high"] - numeric["low"]) / numeric["close"]
    extreme_range = range_pct > max_range_pct
    issue = _issue_from_mask(data.assign(range_pct=range_pct, **numeric), extreme_range, "warning", "extreme_range", f"Candle high-low range exceeds {max_range_pct:.2%}", ["open", "high", "low", "close", "range_pct"])
    if issue:
        issues.append(issue)

    report = _build_report(data, timeframe, issues, expected_bars=len(full_index))
    report["zero_volume_fraction"] = zero_fraction
    report["median_close"] = float(numeric["close"].median()) if numeric["close"].notna().any() else None
    report["max_abs_log_return"] = float(log_ret.abs().max()) if log_ret.notna().any() else None
    report["max_range_pct"] = float(range_pct.max()) if range_pct.notna().any() else None
    return report, pd.DataFrame([asdict(i) for i in issues])


def _build_report(data: pd.DataFrame, timeframe: str, issues: list[QualityIssue], expected_bars: int | None) -> dict[str, Any]:
    severity_order = {"info": 0, "warning": 1, "critical": 2}
    worst = "info"
    for issue in issues:
        if severity_order.get(issue.severity, 0) > severity_order.get(worst, 0):
            worst = issue.severity
    critical_count = sum(1 for i in issues if i.severity == "critical")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    return {
        "timeframe": timeframe,
        "rows": int(len(data)),
        "expected_bars": None if expected_bars is None else int(expected_bars),
        "start": _ts(data.index.min()) if len(data) else None,
        "end": _ts(data.index.max()) if len(data) else None,
        "issue_count": int(len(issues)),
        "critical_count": int(critical_count),
        "warning_count": int(warning_count),
        "status": "pass" if critical_count == 0 else "fail",
        "worst_severity": worst,
    }


def save_quality_artifacts(report: dict[str, Any], issues: pd.DataFrame, output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "data_quality_report.json"
    issues_path = out / "data_quality_issues.csv"
    html_path = out / "data_quality_report.html"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    issues.to_csv(issues_path, index=False, encoding="utf-8-sig")
    _write_quality_html(report, issues, html_path)
    return {"report": str(report_path), "issues": str(issues_path), "html": str(html_path)}


def _write_quality_html(report: dict[str, Any], issues: pd.DataFrame, path: Path) -> None:
    rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in report.items())
    issue_html = issues.to_html(index=False, escape=True) if not issues.empty else "<p>No issues detected.</p>"
    css = """
    <style>
    body{font-family:Arial, sans-serif; margin:24px; color:#1f2937;}
    .card{border:1px solid #e5e7eb; border-radius:16px; padding:18px; margin-bottom:18px; box-shadow:0 2px 10px rgba(0,0,0,.04)}
    table{border-collapse:collapse; width:100%; font-size:14px} th,td{border:1px solid #e5e7eb; padding:8px; text-align:left; vertical-align:top}
    th{background:#f9fafb}.pass{color:#047857;font-weight:700}.fail{color:#b91c1c;font-weight:700}
    </style>
    """
    status_class = "pass" if report.get("status") == "pass" else "fail"
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>Data Quality Report</title>{css}</head><body>
    <h1>BTC Quant Data Quality Report</h1>
    <div class='card'><h2>Status: <span class='{status_class}'>{report.get('status')}</span></h2><table>{rows}</table></div>
    <div class='card'><h2>Issues</h2>{issue_html}</div>
    </body></html>"""
    path.write_text(html, encoding="utf-8")
