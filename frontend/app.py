from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd
import streamlit as st

from crypto_quant.config import resolve_path
from crypto_quant.ui.dashboard_helpers import (
    collect_core_status,
    file_status,
    latest_sqlite_table,
    load_yaml,
    read_csv,
    read_json,
    read_parquet,
    safe_run_script,
    sqlite_table_counts,
    summarize_dataset,
    summarize_model,
)

st.set_page_config(
    page_title="BTC Quant Research Console",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
.btc-card {
    border: 1px solid rgba(120,120,120,.18);
    border-radius: 8px;
    padding: 1rem 1.1rem;
    background: rgba(255,255,255,.035);
}
.small-note {font-size: .88rem; color: #777;}
.good {color: #0a8f48; font-weight: 700;}
.warn {color: #b7791f; font-weight: 700;}
.bad {color: #c53030; font-weight: 700;}
code {border-radius: 8px;}
div[data-testid="stMetric"] {
    border: 1px solid rgba(120,120,120,.18);
    border-radius: 8px;
    padding: .65rem .75rem;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

cfg = load_yaml()
project_cfg = cfg.get("project", {})
symbol_cfg = cfg.get("symbol", {})
exchange_cfg = cfg.get("exchange", {})

st.sidebar.title("₿ BTC Quant Console")
st.sidebar.caption(
    f"{project_cfg.get('version', 'n/a')} · {exchange_cfg.get('name', 'exchange')} · "
    f"{symbol_cfg.get('okx_inst_id') or symbol_cfg.get('ccxt_symbol', 'symbol')}"
)
page = st.sidebar.radio(
    "功能区",
    [
        "总览",
        "数据与模型",
        "实时行情",
        "数据质量与真实性",
        "概率校准与信号可信度",
        "Walk-forward校准",
        "模型库增强",
        "序列模型实验",
        "统一排行榜与准入",
        "运营日报",
        "策略研究",
        "模拟盘",
        "风控与只读影子",
        "流程中心",
        "软件审查",
    ],
)

st.sidebar.markdown("---")
live_enabled = bool(cfg.get("live_trading", {}).get("master_enable", False))
ui_live = bool(cfg.get("ui", {}).get("allow_live_actions", False))
broker_live = bool(cfg.get("broker", {}).get("safety", {}).get("allow_live_trading", False))
st.sidebar.metric("Live Gate", "Blocked" if not (live_enabled and ui_live and broker_live) else "Enabled")
st.sidebar.caption("Research · Paper · Shadow")

RUN_HISTORY_LIMIT = 8


def show_file_table():
    status_df = collect_core_status(cfg)
    if not status_df.empty:
        status_df["size_kb"] = (status_df["size_bytes"] / 1024).round(1)
        st.dataframe(status_df[["path", "exists", "size_kb", "modified"]], use_container_width=True, hide_index=True)


def _button_key(label: str, script: str, args: list[str] | None = None) -> str:
    suffix = "_".join(list(args or []))
    return f"run::{script}::{label}::{suffix}"


def _record_run(script: str, args: list[str], code: int, output: str, elapsed_seconds: float) -> None:
    history = st.session_state.setdefault("run_history", [])
    history.insert(
        0,
        {
            "time": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "script": script,
            "args": " ".join(args),
            "code": code,
            "seconds": round(elapsed_seconds, 1),
            "output": output[-12000:],
        },
    )
    del history[RUN_HISTORY_LIMIT:]


def run_button(
    label: str,
    script: str,
    args: list[str] | None = None,
    help_text: str | None = None,
    key: str | None = None,
    artifacts: list[str | Path | tuple[str, str | Path]] | None = None,
    timeout_seconds: int = 900,
):
    button_key = key or _button_key(label, script, args)
    if st.button(label, help=help_text, use_container_width=True, key=button_key):
        run_args = list(args or [])
        with st.spinner(f"运行 {script} ..."):
            started = pd.Timestamp.utcnow()
            code, out = safe_run_script(script, run_args, timeout_seconds=timeout_seconds)
            elapsed = (pd.Timestamp.utcnow() - started).total_seconds()
        _record_run(script, run_args, code, out or "", elapsed)
        if code == 0:
            st.success(f"{script} 运行完成，用时 {elapsed:.1f}s")
        else:
            st.error(f"{script} 返回码：{code}")
        if artifacts:
            st.dataframe(artifact_status_table(artifacts), use_container_width=True, hide_index=True)
        with st.expander("运行输出", expanded=code != 0):
            st.code(out or "<no output>", language="text")


def _state(ok: bool, ready: str = "就绪", missing: str = "待处理") -> str:
    return ready if ok else missing


def _size_mb(size_bytes: int | None) -> str:
    if not size_bytes:
        return "0.00"
    return f"{size_bytes / 1024 / 1024:.2f}"


def _path_row(label: str, path: str | Path) -> dict[str, object]:
    status = file_status(resolve_path(path))
    return {
        "组件": label,
        "状态": _state(status.exists),
        "路径": status.path,
        "大小MB": _size_mb(status.size_bytes),
        "更新时间": status.modified or "",
    }


def realtime_overview() -> dict[str, object]:
    realtime_cfg = cfg.get("realtime", {})
    db_path = resolve_path(realtime_cfg.get("database_path", "data/database/realtime_market.sqlite"))
    status_df = latest_sqlite_table(db_path, "realtime_status", limit=1, order_by="updated_at")
    kline_df = latest_sqlite_table(db_path, "realtime_klines", limit=1, order_by="timestamp")
    if status_df.empty and kline_df.empty:
        return {"状态": "未初始化", "最新价": "n/a", "最近K线": "n/a", "消息数": 0, "错误": ""}
    status_row = status_df.iloc[0].to_dict() if not status_df.empty else {}
    kline_row = kline_df.iloc[0].to_dict() if not kline_df.empty else {}
    latest_close = kline_row.get("close")
    return {
        "状态": status_row.get("status", "n/a"),
        "最新价": f"{float(latest_close):,.2f}" if latest_close is not None else "n/a",
        "最近K线": kline_row.get("timestamp") or status_row.get("last_kline_at") or "n/a",
        "消息数": status_row.get("message_count", 0),
        "错误": status_row.get("last_error") or "",
    }


def _json_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def realtime_health_snapshot(db_path: str | Path, component: str = "okx_realtime_ws") -> dict[str, object]:
    status_df = latest_sqlite_table(db_path, "realtime_status", limit=20, order_by="updated_at")
    if not status_df.empty and "component" in status_df.columns:
        filtered = status_df[status_df["component"] == component]
        if not filtered.empty:
            status_df = filtered.head(1)
        else:
            status_df = status_df.head(1)
    if status_df.empty:
        return {
            "status": "未初始化",
            "message_count": 0,
            "kline_count": 0,
            "last_error": "",
            "updated_at": "",
            "details": {},
            "severity": "missing",
        }
    row = status_df.iloc[0].to_dict()
    details = _json_dict(row.get("details_json"))
    status = str(row.get("status") or "n/a")
    last_error = str(row.get("last_error") or "")
    severity = "ok"
    if status in {"error", "closed_after_error", "error_stopped"} or last_error:
        severity = "error"
    elif status in {"reconnecting", "closed"}:
        severity = "warn"
    return {
        "component": row.get("component") or component,
        "status": status,
        "message_count": int(row.get("message_count") or 0),
        "kline_count": int(row.get("kline_count") or 0),
        "last_message_at": row.get("last_message_at") or "",
        "last_kline_at": row.get("last_kline_at") or "",
        "last_error": last_error,
        "updated_at": row.get("updated_at") or "",
        "details": details,
        "severity": severity,
    }


def realtime_recovery_rows(snapshot: dict[str, object]) -> pd.DataFrame:
    details = _json_dict(snapshot.get("details"))
    error = _json_dict(details.get("error"))
    rows = []
    if error:
        rows.append({"项目": "错误类型", "值": error.get("category", "network_error")})
        rows.append({"项目": "错误代码", "值": error.get("code", "n/a")})
        rows.append({"项目": "是否可重试", "值": error.get("retryable", "n/a")})
        rows.append({"项目": "摘要", "值": error.get("summary", snapshot.get("last_error", ""))})
    rows.extend([
        {"项目": "当前尝试", "值": details.get("attempt") or details.get("attempts") or "n/a"},
        {"项目": "下次尝试", "值": details.get("next_attempt", "n/a")},
        {"项目": "最大重连", "值": details.get("max_reconnects", "n/a")},
        {"项目": "等待秒数", "值": details.get("sleep_seconds", "n/a")},
    ])
    return pd.DataFrame(rows)


def paper_overview() -> dict[str, object]:
    paper_db = resolve_path(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    counts = sqlite_table_counts(paper_db)
    equity = latest_sqlite_table(paper_db, "equity_curve", limit=1, order_by="timestamp")
    account = latest_sqlite_table(paper_db, "account_state", limit=1, order_by="updated_at")
    equity_row = equity.iloc[0].to_dict() if not equity.empty else {}
    account_row = account.iloc[0].to_dict() if not account.empty else {}
    value = equity_row.get("equity", account_row.get("equity"))
    return {
        "状态": "就绪" if not counts.empty else "未初始化",
        "表数": len(counts) if not counts.empty else 0,
        "权益": f"{float(value):,.2f}" if value is not None else "n/a",
        "最近更新": equity_row.get("timestamp") or account_row.get("updated_at") or "n/a",
    }


def safety_overview() -> pd.DataFrame:
    broker_safety = cfg.get("broker", {}).get("safety", {})
    rows = [
        {"开关": "live_trading.master_enable", "期望": "False", "当前": cfg.get("live_trading", {}).get("master_enable", False)},
        {"开关": "ui.allow_live_actions", "期望": "False", "当前": cfg.get("ui", {}).get("allow_live_actions", False)},
        {"开关": "broker.safety.allow_live_trading", "期望": "False", "当前": broker_safety.get("allow_live_trading", False)},
        {"开关": "broker.safety.default_dry_run", "期望": "True", "当前": broker_safety.get("default_dry_run", True)},
        {"开关": "execution.execute_demo_orders", "期望": "False", "当前": cfg.get("execution", {}).get("execute_demo_orders", False)},
        {"开关": "shadow_live.forbid_order_submission", "期望": "True", "当前": cfg.get("shadow_live", {}).get("forbid_order_submission", True)},
    ]
    for row in rows:
        row["状态"] = "通过" if str(row["当前"]) == row["期望"] else "复核"
    return pd.DataFrame(rows)


def docs_overview() -> pd.DataFrame:
    docs = [
        ("文档索引", "docs/INDEX.md"),
        ("系统架构", "docs/SYSTEM_ARCHITECTURE.md"),
        ("运行模型", "docs/OPERATING_MODEL.md"),
        ("数据与产物", "docs/DATA_AND_ARTIFACTS.md"),
        ("扩展接口", "docs/EXTENSION_INTERFACES.md"),
        ("路线图", "docs/ROADMAP.md"),
        ("OKX实时行情", "docs/OKX_REALTIME_MARKET_DATA.md"),
        ("GitHub资料", "docs/GITHUB_REPOSITORY_PROFILE.md"),
        ("V3.0.7发布说明", "RELEASE_NOTES_V3_0_7.md"),
        ("V3.0.6发布说明", "RELEASE_NOTES_V3_0_6.md"),
    ]
    return pd.DataFrame([_path_row(label, path) for label, path in docs])


def artifact_status_table(artifacts: list[str | Path | tuple[str, str | Path]]) -> pd.DataFrame:
    rows = []
    for item in artifacts:
        if isinstance(item, tuple):
            label, path = item
        else:
            path = item
            label = Path(path).name
        rows.append(_path_row(str(label), path))
    return pd.DataFrame(rows)


def run_history_panel() -> None:
    history = st.session_state.get("run_history", [])
    if not history:
        st.info("本次会话尚无运行记录。")
        return
    rows = [{k: v for k, v in item.items() if k != "output"} for item in history]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    latest = history[0]
    with st.expander(f"最近输出：{latest['script']}", expanded=False):
        st.code(latest.get("output") or "<no output>", language="text")


def _workflow_groups() -> dict[str, list[dict[str, object]]]:
    data_cfg = cfg.get("data", {})
    model_cfg = cfg.get("model", {})
    calibration_cfg = cfg.get("calibration", {})
    deployment_cfg = cfg.get("deployment", {})
    paper_cfg = cfg.get("paper", {})
    realtime_cfg = cfg.get("realtime", {})
    operations_cfg = cfg.get("operations", {})
    model_admission_cfg = cfg.get("model_admission", {})
    return {
        "基础构建": [
            {
                "label": "部署健康检查",
                "script": "deploy_check.py",
                "outputs": [("健康报告", deployment_cfg.get("health_report_path", "reports/deployment/health_report.json"))],
            },
            {
                "label": "下载公开K线",
                "script": "download_ohlcv.py",
                "outputs": [("原始K线", data_cfg.get("raw_path", "data/raw/OKX_BTC_USDT_SWAP_4h.parquet"))],
            },
            {
                "label": "检查K线质量",
                "script": "run_data_quality_check.py",
                "outputs": [("数据质量报告", "reports/data_quality/data_quality_report.json")],
            },
            {
                "label": "构建特征与标签",
                "script": "build_features.py",
                "outputs": [
                    ("特征数据", data_cfg.get("feature_path", "data/processed/OKX_BTC_USDT_SWAP_4h_features.parquet")),
                    ("训练数据集", data_cfg.get("dataset_path", "data/processed/OKX_BTC_USDT_SWAP_4h_dataset.parquet")),
                ],
            },
            {
                "label": "训练方向模型",
                "script": "train_model.py",
                "outputs": [
                    ("模型文件", model_cfg.get("model_path", "models/btc_direction_model.joblib")),
                    ("特征列表", model_cfg.get("feature_list_path", "models/btc_feature_columns.txt")),
                ],
            },
            {
                "label": "模型诊断",
                "script": "run_model_diagnostics.py",
                "outputs": [("模型诊断", "reports/model_diagnostics/model_diagnostics_summary.json")],
            },
        ],
        "研究评估": [
            {
                "label": "训练校准模型",
                "script": "train_calibrated_model.py",
                "outputs": [
                    ("校准模型", calibration_cfg.get("calibrated_model_path", "models/btc_direction_model_calibrated.joblib")),
                    ("校准指标", "reports/calibration/calibration_metrics.json"),
                ],
            },
            {
                "label": "信号可信度报告",
                "script": "run_signal_confidence_report.py",
                "outputs": [("信号分层", "reports/signal_confidence/confidence_tier_table.csv")],
            },
            {
                "label": "Walk-forward校准",
                "script": "run_walk_forward_calibration.py",
                "outputs": [("WF校准摘要", "reports/walk_forward_calibration/walk_forward_calibration_summary.json")],
            },
            {
                "label": "严格CV验证",
                "script": "run_purged_embargo_cv.py",
                "outputs": [("CV报告", "reports/validation/purged_embargo_cv_report.json")],
            },
            {
                "label": "策略参数搜索",
                "script": "run_strategy_parameter_search.py",
                "outputs": [("参数搜索", "reports/robustness/parameter_search/strategy_parameter_search_summary.csv")],
            },
            {
                "label": "组合策略回测",
                "script": "run_ensemble_strategy.py",
                "outputs": [("组合策略", "reports/ensemble/ensemble_summary.csv")],
            },
            {
                "label": "统一排行榜",
                "script": "run_model_strategy_admission.py",
                "outputs": [
                    ("准入摘要", f"{model_admission_cfg.get('output_path', 'reports/model_admission')}/model_strategy_admission_summary.json"),
                    ("排行榜", f"{model_admission_cfg.get('output_path', 'reports/model_admission')}/model_strategy_leaderboard.csv"),
                ],
            },
        ],
        "模拟运营": [
            {
                "label": "初始化模拟盘",
                "script": "paper_init.py",
                "args": ["--reset"],
                "outputs": [("模拟盘数据库", paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))],
            },
            {
                "label": "回放组合模拟盘",
                "script": "paper_ensemble_replay_dataset.py",
                "args": ["--bars", "300", "--reset"],
                "outputs": [("模拟盘数据库", paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))],
            },
            {
                "label": "组合策略预览",
                "script": "paper_ensemble_preview.py",
                "outputs": [("组合模拟盘报告", "reports/ensemble_paper/ensemble_paper_preview.csv")],
            },
            {
                "label": "Paper健康检查",
                "script": "run_paper_health_check.py",
                "outputs": [("Paper健康", "reports/operations/paper_health_report.json")],
            },
            {
                "label": "信号命中率报告",
                "script": "run_signal_hit_rate_report.py",
                "outputs": [("信号命中率", "reports/operations/daily_signal_hit_rate_by_tier.csv")],
            },
            {
                "label": "生成运营日报",
                "script": "run_daily_operations_report.py",
                "outputs": [("运营摘要", f"{operations_cfg.get('output_path', 'reports/operations')}/daily_operations_summary.json")],
            },
            {
                "label": "生成V3.0总报告",
                "script": "build_v30_operations_report.py",
                "outputs": [("V3.0报告", "reports/v3_0_operations_report/v3_0_operations_report.html")],
            },
        ],
        "实时行情": [
            {
                "label": "采样实时行情",
                "script": "run_okx_realtime_listener.py",
                "args": ["--max-messages", "5"],
                "outputs": [("实时数据库", realtime_cfg.get("database_path", "data/database/realtime_market.sqlite"))],
            },
            {
                "label": "查看实时状态",
                "script": "run_realtime_status.py",
                "outputs": [("实时数据库", realtime_cfg.get("database_path", "data/database/realtime_market.sqlite"))],
            },
            {
                "label": "合并4H实时K线",
                "script": "merge_realtime_ohlcv.py",
                "outputs": [("原始K线", data_cfg.get("raw_path", "data/raw/OKX_BTC_USDT_SWAP_4h.parquet"))],
            },
        ],
    }


def _step_status(step: dict[str, object]) -> str:
    outputs = step.get("outputs", [])
    if not outputs:
        return "可运行"
    table = artifact_status_table(outputs)  # type: ignore[arg-type]
    exists = table["状态"].eq("就绪")
    if bool(exists.all()):
        return "已生成"
    if bool(exists.any()):
        return "部分生成"
    return "待运行"


def workflow_status_table(steps: list[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for idx, step in enumerate(steps, start=1):
        args = " ".join(step.get("args", [])) if isinstance(step.get("args", []), list) else ""
        outputs = step.get("outputs", [])
        output_labels = []
        for item in outputs if isinstance(outputs, list) else []:
            output_labels.append(str(item[0] if isinstance(item, tuple) else Path(str(item)).name))
        rows.append(
            {
                "序号": idx,
                "步骤": step["label"],
                "状态": _step_status(step),
                "脚本": step["script"],
                "参数": args,
                "产物": " / ".join(output_labels),
            }
        )
    return pd.DataFrame(rows)


def render_workflow(name: str, steps: list[dict[str, object]], key_prefix: str) -> None:
    table = workflow_status_table(steps)
    done = int(table["状态"].eq("已生成").sum()) if not table.empty else 0
    st.metric(f"{name}进度", f"{done}/{len(steps)}")
    st.progress(done / max(len(steps), 1))
    st.dataframe(table, use_container_width=True, hide_index=True)

    options = [f"{idx + 1}. {step['label']}" for idx, step in enumerate(steps)]
    selected_label = st.selectbox("步骤", options, key=f"{key_prefix}_select")
    selected_idx = options.index(selected_label)
    selected = steps[selected_idx]
    c1, c2 = st.columns([1, 2])
    with c1:
        run_button(
            "运行选中步骤",
            str(selected["script"]),
            list(selected.get("args", [])),  # type: ignore[arg-type]
            key=f"{key_prefix}_run_{selected_idx}",
            artifacts=selected.get("outputs", []),  # type: ignore[arg-type]
        )
    with c2:
        outputs = selected.get("outputs", [])
        if outputs:
            st.dataframe(artifact_status_table(outputs), use_container_width=True, hide_index=True)  # type: ignore[arg-type]


if page == "总览":
    st.title("系统总览")
    st.caption(f"{project_cfg.get('name', 'btc_quant_framework')} · {project_cfg.get('version', 'n/a')}")

    data_summary = summarize_dataset(cfg)
    model_summary = summarize_model(cfg)
    paper_db = resolve_path(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    realtime = realtime_overview()
    paper = paper_overview()
    safety_df = safety_overview()
    safety_pass = bool((safety_df["状态"] == "通过").all())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dataset Rows", data_summary.get("rows", 0))
    c2.metric("Model", "Ready" if model_summary.get("model_exists") else "Missing")
    c3.metric("Realtime", str(realtime.get("状态", "n/a")))
    c4.metric("Safety", "Blocked" if safety_pass else "Review")

    tabs = st.tabs(["链路", "产物", "安全", "文档"])
    with tabs[0]:
        rows = [
            {"层级": "历史行情", "状态": _state(file_status(resolve_path(cfg.get("data", {}).get("raw_path", ""))).exists), "摘要": cfg.get("data", {}).get("raw_path", "")},
            {"层级": "训练数据集", "状态": _state(bool(data_summary.get("exists"))), "摘要": f"{data_summary.get('rows', 0)} rows / {data_summary.get('columns', 0)} columns"},
            {"层级": "模型文件", "状态": _state(bool(model_summary.get("model_exists"))), "摘要": f"{model_summary.get('feature_count', 0)} features"},
            {"层级": "实时行情", "状态": str(realtime.get("状态", "n/a")), "摘要": f"price={realtime.get('最新价')} · messages={realtime.get('消息数')}"},
            {"层级": "模拟盘", "状态": str(paper.get("状态", "n/a")), "摘要": f"equity={paper.get('权益')} · tables={paper.get('表数')}"},
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if realtime.get("错误"):
            st.warning(str(realtime["错误"]))
        st.markdown("### 快速动作")
        q1, q2, q3, q4 = st.columns(4)
        with q1:
            run_button(
                "采样实时行情",
                "run_okx_realtime_listener.py",
                ["--max-messages", "5"],
                key="overview_sample_realtime",
                artifacts=[("实时数据库", cfg.get("realtime", {}).get("database_path", "data/database/realtime_market.sqlite"))],
            )
        with q2:
            run_button(
                "数据质量检查",
                "run_data_quality_check.py",
                key="overview_data_quality",
                artifacts=[("数据质量报告", "reports/data_quality/data_quality_report.json")],
            )
        with q3:
            run_button(
                "生成运营日报",
                "run_daily_operations_report.py",
                key="overview_daily_ops",
                artifacts=[("运营摘要", "reports/operations/daily_operations_summary.json")],
            )
        with q4:
            run_button(
                "安全检查",
                "deploy_check.py",
                key="overview_deploy_check",
                artifacts=[("健康报告", cfg.get("deployment", {}).get("health_report_path", "reports/deployment/health_report.json"))],
            )

    with tabs[1]:
        artifacts = [
            _path_row("原始K线", cfg.get("data", {}).get("raw_path", "data/raw/OKX_BTC_USDT_SWAP_4h.parquet")),
            _path_row("特征数据", cfg.get("data", {}).get("feature_path", "data/processed/OKX_BTC_USDT_SWAP_4h_features.parquet")),
            _path_row("训练数据集", cfg.get("data", {}).get("dataset_path", "data/processed/OKX_BTC_USDT_SWAP_4h_dataset.parquet")),
            _path_row("实时数据库", cfg.get("realtime", {}).get("database_path", "data/database/realtime_market.sqlite")),
            _path_row("模拟盘数据库", paper_db),
            _path_row("模型", cfg.get("model", {}).get("model_path", "models/btc_direction_model.joblib")),
            _path_row("准入报告", "reports/model_admission/model_strategy_admission_report.html"),
            _path_row("运营日报", "reports/operations/daily_operations_report.html"),
        ]
        st.dataframe(pd.DataFrame(artifacts), use_container_width=True, hide_index=True)

    with tabs[2]:
        st.dataframe(safety_df, use_container_width=True, hide_index=True)

    with tabs[3]:
        st.dataframe(docs_overview(), use_container_width=True, hide_index=True)

elif page == "数据与模型":
    st.title("数据与模型训练")
    data_cfg = cfg.get("data", {})
    model_cfg = cfg.get("model", {})

    st.markdown("### 数据配置")
    st.json({"symbol": cfg.get("symbol", {}), "data": data_cfg, "labels": cfg.get("labels", {}), "model": model_cfg})

    st.markdown("### 数据集摘要")
    summary = summarize_dataset(cfg)
    st.json(summary)

    dataset = read_parquet(data_cfg.get("dataset_path", "data/processed/BTCUSDT_4h_dataset.parquet"), nrows=500)
    if not dataset.empty:
        st.markdown("### 最近数据预览")
        st.dataframe(dataset.tail(100), use_container_width=True)
        if "close" in dataset.columns:
            st.markdown("### 收盘价走势")
            st.line_chart(dataset[["close"]])
        if "future_return" in dataset.columns:
            st.markdown("### 未来收益标签分布")
            st.bar_chart(dataset["label_up"].value_counts().sort_index() if "label_up" in dataset else dataset["future_return"])

    st.markdown("### 模型状态")
    st.json(summarize_model(cfg))

    st.markdown("### 安全运行按钮")
    col1, col2, col3 = st.columns(3)
    with col1:
        run_button("1. 下载/更新K线", "download_ohlcv.py", help_text="需要联网；只下载公开行情数据。")
    with col2:
        run_button("2. 构建特征与标签", "build_features.py")
    with col3:
        run_button("3. 训练方向模型", "train_model.py")
    run_button("运行模型诊断", "run_model_diagnostics.py")


elif page == "实时行情":
    st.title("OKX 实时行情")
    realtime_cfg = cfg.get("realtime", {})
    inst_id = realtime_cfg.get("inst_id") or cfg.get("symbol", {}).get("okx_inst_id", "BTC-USDT-SWAP")
    channels = realtime_cfg.get("channels", ["candle1m", "candle4H"]) or ["candle1m"]
    db_path = resolve_path(realtime_cfg.get("database_path", "data/database/realtime_market.sqlite"))
    component = str(realtime_cfg.get("status_component", "okx_realtime_ws"))

    st.markdown("### 连接健康")
    snapshot = realtime_health_snapshot(db_path, component=component)
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("状态", str(snapshot.get("status", "n/a")))
    h2.metric("消息数", snapshot.get("message_count", 0))
    h3.metric("K线数", snapshot.get("kline_count", 0))
    h4.metric("最近更新", str(snapshot.get("updated_at") or "n/a"))
    last_error = str(snapshot.get("last_error") or "")
    if snapshot.get("severity") == "error":
        st.warning(last_error or "实时连接最近发生错误。")
        recovery = realtime_recovery_rows(snapshot)
        if not recovery.empty:
            st.dataframe(recovery, use_container_width=True, hide_index=True)
        if "10054" in last_error or "connection_reset" in last_error:
            st.info("10054 通常表示远端或中间网络主动断开连接。系统会把它作为可恢复网络错误记录，并按重连参数继续尝试。")
    elif snapshot.get("severity") == "warn":
        st.info("实时连接处于关闭或重连状态，可先运行下方采样按钮确认网络。")
    else:
        st.success("实时连接状态正常或尚未发现错误。")

    st.markdown("### 实时数据库")
    st.write(str(db_path))
    counts = sqlite_table_counts(db_path)
    if counts.empty:
        st.warning("实时行情数据库尚未初始化。")
    else:
        st.dataframe(counts, use_container_width=True, hide_index=True)

    st.markdown("### 连接状态")
    status_df = latest_sqlite_table(db_path, "realtime_status", limit=20, order_by="updated_at")
    if status_df.empty:
        st.info("尚未记录 WebSocket 状态。")
    else:
        st.dataframe(status_df, use_container_width=True, hide_index=True)

    st.markdown("### 最新K线")
    channel = st.selectbox("频道", channels, index=0)
    latest = latest_sqlite_table(db_path, "realtime_klines", limit=int(cfg.get("ui", {}).get("max_table_rows", 300)), order_by="timestamp")
    if not latest.empty:
        latest = latest[(latest["inst_id"] == inst_id) & (latest["channel"] == channel)]
    if latest.empty:
        st.warning("尚未写入实时K线。")
    else:
        latest_sorted = latest.copy()
        latest_sorted["timestamp"] = pd.to_datetime(latest_sorted["timestamp"], errors="coerce", utc=True)
        latest_sorted = latest_sorted.sort_values("timestamp")
        row = latest_sorted.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("最新价格", f"{float(row['close']):,.2f}")
        c2.metric("频道", str(row["channel"]))
        c3.metric("确认", "是" if int(row.get("confirm", 0)) else "否")
        c4.metric("记录数", len(latest_sorted))
        if "close" in latest_sorted.columns:
            st.line_chart(latest_sorted.set_index("timestamp")[["close"]])
        display_cols = [
            c for c in [
                "timestamp", "inst_id", "channel", "open", "high", "low", "close",
                "volume", "confirm", "received_at", "updated_at",
            ] if c in latest_sorted.columns
        ]
        st.dataframe(latest_sorted[display_cols].tail(100), use_container_width=True, hide_index=True)

    st.markdown("### 安全运行按钮")
    sample_messages = st.number_input("采样消息数", min_value=1, max_value=200, value=5, step=1)
    sample_reconnects = st.number_input(
        "采样重连次数",
        min_value=0,
        max_value=20,
        value=int(realtime_cfg.get("max_reconnects", 3)),
        step=1,
    )
    reconnect_sleep = st.number_input(
        "重连等待秒数",
        min_value=1,
        max_value=60,
        value=int(realtime_cfg.get("reconnect_sleep_seconds", 3)),
        step=1,
    )
    ignore_env_proxy = st.checkbox("忽略系统代理", value=False)
    sample_args = [
        "--max-messages", str(int(sample_messages)),
        "--reconnects", str(int(sample_reconnects)),
        "--reconnect-sleep-seconds", str(int(reconnect_sleep)),
    ]
    if ignore_env_proxy:
        sample_args.append("--no-env-proxy")
    c1, c2, c3 = st.columns(3)
    with c1:
        run_button(
            "采样实时行情",
            "run_okx_realtime_listener.py",
            sample_args,
            help_text="采样接收少量公开行情消息后自动停止。",
            key="realtime_sample_messages",
            artifacts=[("实时数据库", db_path)],
        )
    with c2:
        run_button("查看实时状态", "run_realtime_status.py", artifacts=[("实时数据库", db_path)])
    with c3:
        run_button(
            "合并4H实时K线",
            "merge_realtime_ohlcv.py",
            help_text="仅合并已确认的4H K线。",
            artifacts=[("原始K线", cfg.get("data", {}).get("raw_path", "data/raw/OKX_BTC_USDT_SWAP_4h.parquet"))],
        )
    run_button(
        "OKX REST连通性诊断",
        "check_okx_connectivity.py",
        help_text="测试 OKX public/time、ticker、candles、history-candles。",
        timeout_seconds=120,
    )


elif page == "数据质量与真实性":
    st.title("数据质量、回测真实性与严格验证")
    st.caption("V2.4：先检查数据，再检查回测是否低估成本和杠杆风险，最后用 Purged/Embargo CV 检查模型稳健性。")

    paths = {
        "数据质量报告": "reports/data_quality/data_quality_report.json",
        "资金费率下载报告": "reports/market_realism/funding_download_report.json",
        "回测真实性报告": "reports/market_realism/market_realism_report.json",
        "Purged/Embargo CV报告": "reports/validation/purged_embargo_cv_report.json",
    }
    cols = st.columns(4)
    for col, (name, path) in zip(cols, paths.items()):
        obj = read_json(path)
        if obj is None:
            col.metric(name, "未生成")
        else:
            status = obj.get("status") or obj.get("folds") or "已生成"
            col.metric(name, status)

    st.markdown("### 数据质量问题")
    dq = read_csv("reports/data_quality/data_quality_issues.csv")
    if dq.empty:
        st.info("尚未生成数据质量报告，或未发现问题。")
    else:
        st.dataframe(dq, use_container_width=True)

    st.markdown("### 回测真实性摘要")
    mr = read_json("reports/market_realism/market_realism_report.json")
    if mr is None:
        st.warning("尚未生成回测真实性报告。")
    else:
        st.json(mr)

    st.markdown("### Purged / Embargo CV")
    cv = read_csv("reports/validation/purged_embargo_cv_metrics.csv")
    if cv.empty:
        st.warning("尚未生成严格时间序列交叉验证结果。")
    else:
        st.dataframe(cv, use_container_width=True)

    st.markdown("### V2.4 安全运行按钮")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        run_button("检查K线质量", "run_data_quality_check.py")
    with c2:
        run_button("下载资金费率", "download_funding_rates.py", help_text="需要联网；失败不影响其他研究流程。")
    with c3:
        run_button("生成真实性报告", "run_market_realism_report.py")
    with c4:
        run_button("严格CV验证", "run_purged_embargo_cv.py")

elif page == "概率校准与信号可信度":
    st.title("概率校准与交易信号可信度")
    st.caption("V2.5：把模型原始概率校准后，再分层映射到动态目标敞口，避免直接用未校准概率驱动杠杆。")

    calib_metrics = read_json("reports/calibration/calibration_metrics.json")
    if calib_metrics is None:
        st.warning("尚未生成概率校准报告。请先运行 train_calibrated_model.py。")
    else:
        raw = calib_metrics.get("raw", {})
        cal = calib_metrics.get("calibrated", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Raw Brier", round(raw.get("brier_score", 0), 5))
        c2.metric("Calibrated Brier", round(cal.get("brier_score", 0), 5))
        c3.metric("Raw ECE", round(raw.get("ece", 0), 5))
        c4.metric("Calibrated ECE", round(cal.get("ece", 0), 5))
        st.json(calib_metrics)

    st.markdown("### 可靠性分桶")
    tabs = st.tabs(["Raw", "Calibrated", "信号分层", "回测摘要"])
    with tabs[0]:
        df = read_csv("reports/calibration/reliability_raw.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成 raw reliability 表。")
    with tabs[1]:
        df = read_csv("reports/calibration/reliability_calibrated.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成 calibrated reliability 表。")
    with tabs[2]:
        df = read_csv("reports/signal_confidence/confidence_tier_table.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成 confidence tier 表。")
    with tabs[3]:
        df = read_csv("reports/signal_confidence/confidence_summary.csv")
        if df.empty:
            df = read_csv("reports/calibrated_ml_backtest/calibrated_ml_summary.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成校准策略回测摘要。")

    st.markdown("### 图表")
    img1 = resolve_path("reports/calibration/raw_vs_calibrated_reliability.png")
    img2 = resolve_path("reports/signal_confidence/confidence_equity.png")
    col1, col2 = st.columns(2)
    with col1:
        if img1.exists():
            st.image(str(img1), caption="Raw vs Calibrated Reliability")
    with col2:
        if img2.exists():
            st.image(str(img2), caption="Confidence Strategy Equity")

    st.markdown("### V2.5 安全运行按钮")
    c1, c2, c3 = st.columns(3)
    with c1:
        run_button("训练校准模型", "train_calibrated_model.py")
    with c2:
        run_button("信号可信度报告", "run_signal_confidence_report.py")
    with c3:
        run_button("校准ML回测", "run_calibrated_ml_backtest.py")

elif page == "Walk-forward校准":
    st.title("Walk-forward 概率校准")
    st.caption("V2.6：每个 fold 严格使用 train → calibration → test，校准器不接触测试窗口，适合评估校准概率是否真正样本外稳定。")

    summary = read_json("reports/walk_forward_calibration/walk_forward_calibration_summary.json")
    if summary is None:
        st.warning("尚未生成 Walk-forward 概率校准报告。请运行 run_walk_forward_calibration.py。")
    else:
        raw = summary.get("raw", {})
        cal = summary.get("calibrated", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Folds", summary.get("folds", 0))
        c2.metric("Bars", summary.get("bars", 0))
        c3.metric("Raw Brier", round(raw.get("brier_score", 0), 5))
        c4.metric("Calibrated Brier", round(cal.get("brier_score", 0), 5))
        st.json(summary)

    tabs = st.tabs(["Fold指标", "可靠性", "信号分层", "动态回测"])
    with tabs[0]:
        df = read_csv("reports/walk_forward_calibration/walk_forward_calibrated_folds.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成 fold 指标。")
    with tabs[1]:
        col1, col2 = st.columns(2)
        with col1:
            df = read_csv("reports/walk_forward_calibration/walk_forward_reliability_raw.csv")
            st.markdown("#### Raw")
            st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成 raw reliability。")
        with col2:
            df = read_csv("reports/walk_forward_calibration/walk_forward_reliability_calibrated.csv")
            st.markdown("#### Calibrated")
            st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成 calibrated reliability。")
    with tabs[2]:
        df = read_csv("reports/walk_forward_calibration/walk_forward_confidence_tiers.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成 walk-forward 信号分层。")
    with tabs[3]:
        df = read_csv("reports/walk_forward_calibration/walk_forward_calibrated_summary.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成 walk-forward 动态回测摘要。")

    st.markdown("### 图表")
    img1 = resolve_path("reports/walk_forward_calibration/walk_forward_reliability.png")
    img2 = resolve_path("reports/walk_forward_calibration/walk_forward_calibrated_equity.png")
    col1, col2 = st.columns(2)
    with col1:
        if img1.exists():
            st.image(str(img1), caption="Walk-forward Reliability")
    with col2:
        if img2.exists():
            st.image(str(img2), caption="Walk-forward Calibrated Equity")

    st.markdown("### V2.6 安全运行按钮")
    c1, c2 = st.columns(2)
    with c1:
        run_button("运行Walk-forward校准", "run_walk_forward_calibration.py")
    with c2:
        run_button("生成V2.6研究报告", "build_v26_research_report.py")


elif page == "模型库增强":
    st.title("模型库增强与可选后端")
    st.caption("V2.7：LightGBM / XGBoost 为可选依赖；未安装时自动跳过，默认模型链路仍然可运行。")

    st.markdown("### 后端可用性")
    backend = read_csv("reports/model_backends/model_backend_availability.csv")
    if backend.empty:
        st.info("尚未生成模型后端检查。请运行 check_model_backends.py。")
    else:
        st.dataframe(backend, use_container_width=True)

    st.markdown("### 可选依赖状态")
    deps = read_csv("reports/model_backends/optional_dependency_status.csv")
    if deps.empty:
        st.info("尚未生成可选依赖状态。")
    else:
        st.dataframe(deps, use_container_width=True)

    tabs = st.tabs(["增强模型库", "跳过模型", "Walk-forward校准模型库"])
    with tabs[0]:
        df = read_csv("reports/enhanced_model_library/model_library_summary.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.warning("尚未生成增强模型库结果。")
    with tabs[1]:
        df = read_csv("reports/enhanced_model_library/skipped_models.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("没有跳过模型，或报告尚未生成。")
    with tabs[2]:
        df = read_csv("reports/walk_forward_calibration_model_library/walk_forward_calibration_model_library_summary.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.warning("尚未生成 walk-forward 校准模型库结果。")

    st.markdown("### V2.7 安全运行按钮")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        run_button("检查模型后端", "check_model_backends.py")
    with c2:
        run_button("增强模型库诊断", "run_enhanced_model_library.py")
    with c3:
        run_button("WF校准模型库", "run_wf_calibration_model_library.py")
    with c4:
        run_button("生成V2.7报告", "build_v27_research_report.py")


elif page == "序列模型实验":
    st.title("序列模型实验层")
    st.caption("V2.8：LSTM / GRU / TCN 只作为研究实验层；默认仅启用无额外依赖的 sequence_mlp，不接模拟盘执行或实盘。")

    summary_json = read_json("reports/sequence_models/sequence_model_experiment_summary.json")
    wf_json = read_json("reports/sequence_walk_forward/sequence_walk_forward_summary.json")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("固定切分状态", (summary_json or {}).get("status", "未生成"))
    c2.metric("序列样本", (summary_json or {}).get("total_sequences", 0))
    c3.metric("WF状态", (wf_json or {}).get("status", "未生成"))
    c4.metric("WF模型数", len((wf_json or {}).get("models", [])))

    st.markdown("### 序列模型后端")
    backend = read_csv("reports/sequence_models/sequence_model_availability.csv")
    if backend.empty:
        st.info("尚未生成序列模型后端检查。")
    else:
        st.dataframe(backend, use_container_width=True)

    tabs = st.tabs(["固定切分", "Walk-forward", "可靠性", "跳过模型"])
    with tabs[0]:
        df = read_csv("reports/sequence_models/sequence_model_summary.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.warning("尚未生成固定切分序列模型结果。")
    with tabs[1]:
        df = read_csv("reports/sequence_walk_forward/sequence_walk_forward_summary.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.warning("尚未生成 sequence walk-forward 结果。")
        folds = read_csv("reports/sequence_walk_forward/sequence_walk_forward_folds.csv")
        if not folds.empty:
            st.markdown("#### Fold 明细")
            st.dataframe(folds, use_container_width=True)
    with tabs[2]:
        df = read_csv("reports/sequence_walk_forward/sequence_walk_forward_reliability.csv")
        if df.empty:
            df = read_csv("reports/sequence_models/sequence_model_reliability.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("尚未生成可靠性分桶。")
    with tabs[3]:
        df1 = read_csv("reports/sequence_models/sequence_model_skipped.csv")
        df2 = read_csv("reports/sequence_walk_forward/sequence_walk_forward_skipped.csv")
        if not df1.empty:
            st.markdown("#### 固定切分跳过")
            st.dataframe(df1, use_container_width=True)
        if not df2.empty:
            st.markdown("#### Walk-forward 跳过")
            st.dataframe(df2, use_container_width=True)
        if df1.empty and df2.empty:
            st.info("没有跳过模型，或报告尚未生成。")

    st.markdown("### 图表")
    img1 = resolve_path("reports/sequence_models/sequence_model_auc.png")
    img2 = resolve_path("reports/sequence_walk_forward/sequence_walk_forward_auc.png")
    col1, col2 = st.columns(2)
    with col1:
        if img1.exists():
            st.image(str(img1), caption="Fixed split sequence model ROC-AUC")
    with col2:
        if img2.exists():
            st.image(str(img2), caption="Walk-forward sequence model ROC-AUC")

    st.markdown("### V2.8 安全运行按钮")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        run_button("检查序列后端", "check_sequence_model_backends.py")
    with c2:
        run_button("固定切分实验", "run_sequence_model_experiments.py")
    with c3:
        run_button("WF序列实验", "run_sequence_walk_forward.py")
    with c4:
        run_button("生成V2.8报告", "build_v28_sequence_report.py")


elif page == "统一排行榜与准入":
    st.title("统一模型排行榜与策略准入")
    st.caption("V2.9：把表格模型、LightGBM/XGBoost、Walk-forward校准、序列模型和组合策略统一排序，并给出 paper_candidate_pool / watchlist / research_only / rejected。")

    summary = read_json("reports/model_admission/model_strategy_admission_summary.json")
    if summary is None:
        st.warning("尚未生成统一准入报告。请运行 run_model_strategy_admission.py。")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("候选总数", summary.get("total_candidates", 0))
        c2.metric("Paper候选", summary.get("paper_candidate_pool", 0))
        c3.metric("观察名单", summary.get("watchlist", 0))
        c4.metric("研究保留", summary.get("research_only", 0))
        c5.metric("淘汰", summary.get("rejected", 0))
        st.json(summary)

    tabs = st.tabs(["排行榜", "准入汇总", "候选宇宙", "图表与报告"])
    with tabs[0]:
        df = read_csv("reports/model_admission/model_strategy_leaderboard.csv")
        if df.empty:
            st.warning("尚未生成排行榜。")
        else:
            cols = [c for c in ["candidate_name", "family", "admission_decision", "admission_score", "calibrated_auc", "auc", "sharpe", "calmar", "max_drawdown", "trades", "folds", "blockers", "warnings"] if c in df.columns]
            st.dataframe(df[cols] if cols else df, use_container_width=True)
    with tabs[1]:
        df = read_csv("reports/model_admission/admission_summary.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成准入汇总。")
    with tabs[2]:
        df = read_csv("reports/model_admission/candidate_universe.csv")
        st.dataframe(df, use_container_width=True) if not df.empty else st.info("未生成候选宇宙。")
    with tabs[3]:
        img = resolve_path("reports/model_admission/leaderboard_top_scores.png")
        if img.exists():
            st.image(str(img), caption="Top candidates by admission score")
        report = resolve_path("reports/model_admission/model_strategy_admission_report.html")
        if report.exists():
            st.success(f"HTML报告已生成：{report}")
        else:
            st.info("尚未生成HTML报告。")

    st.markdown("### V2.9 安全运行按钮")
    c1, c2 = st.columns(2)
    with c1:
        run_button("生成统一排行榜", "run_model_strategy_admission.py")
    with c2:
        run_button("生成V2.9报告", "build_v29_admission_report.py")


elif page == "运营日报":
    st.title("V3.0 模拟盘长期运行与自动研究日报")
    st.caption("聚合模拟盘权益/回撤、目标敞口、准入池变化、概率漂移、滚动命中率和策略失效提醒；不提供实盘下单入口。")

    summary = read_json("reports/operations/daily_operations_summary.json")
    if summary is None:
        st.warning("尚未生成运营日报。请先运行 run_daily_operations_report.py 或 build_v30_operations_report.py。")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Paper Equity", summary.get("paper_latest_equity", "n/a"))
        total_ret = summary.get("paper_total_return")
        c2.metric("Paper Total Return", f"{100*total_ret:.2f}%" if isinstance(total_ret, (int, float)) else "n/a")
        max_dd = summary.get("paper_max_drawdown")
        c3.metric("Max Drawdown", f"{100*max_dd:.2f}%" if isinstance(max_dd, (int, float)) else "n/a")
        c4.metric("Alert Count", summary.get("alert_count", 0))

        st.markdown("### 日报摘要")
        st.json(summary)

    alerts = read_csv("reports/operations/daily_operations_alerts.csv")
    if not alerts.empty:
        st.markdown("### 运营提醒")
        st.dataframe(alerts, use_container_width=True, hide_index=True)

    st.markdown("### 权益与回撤")
    eq_img = resolve_path("reports/operations/paper_equity_curve.png")
    dd_img = resolve_path("reports/operations/paper_drawdown.png")
    col1, col2 = st.columns(2)
    with col1:
        if eq_img.exists():
            st.image(str(eq_img), caption="Paper equity curve", use_container_width=True)
        else:
            st.caption("尚未生成权益曲线图。")
    with col2:
        if dd_img.exists():
            st.image(str(dd_img), caption="Paper drawdown", use_container_width=True)
        else:
            st.caption("尚未生成回撤曲线图。")

    st.markdown("### 准入池与模型/策略候选")
    lb = read_csv("reports/operations/daily_admission_leaderboard_top.csv")
    if lb.empty:
        lb = read_csv("reports/model_admission/model_strategy_leaderboard.csv")
    if lb.empty:
        st.info("尚未生成统一排行榜。")
    else:
        cols = [c for c in ["candidate_name", "family", "admission_decision", "admission_score", "blockers", "warnings"] if c in lb.columns]
        st.dataframe(lb[cols].head(50) if cols else lb.head(50), use_container_width=True, hide_index=True)

    changes = read_csv("reports/operations/daily_admission_changes.csv")
    if not changes.empty:
        st.markdown("### 准入状态变化")
        st.dataframe(changes, use_container_width=True, hide_index=True)

    st.markdown("### 概率漂移与信号命中率")
    ctiers = read_csv("reports/operations/daily_confidence_tier_distribution.csv")
    hit = read_csv("reports/operations/daily_signal_hit_rate_by_tier.csv")
    c1, c2 = st.columns(2)
    with c1:
        st.caption("近期信号分层分布")
        if ctiers.empty:
            st.info("尚未生成信号分层分布。")
        else:
            st.dataframe(ctiers, use_container_width=True, hide_index=True)
    with c2:
        st.caption("按可信度分层的命中率")
        if hit.empty:
            st.info("尚未生成命中率表。")
        else:
            st.dataframe(hit, use_container_width=True, hide_index=True)

    st.markdown("### 模拟盘最近状态")
    tail_tabs = st.tabs(["目标敞口", "订单", "权益尾部"])
    with tail_tabs[0]:
        df = read_csv("reports/operations/daily_target_exposure_tail.csv")
        st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.caption("无目标敞口记录。")
    with tail_tabs[1]:
        df = read_csv("reports/operations/daily_orders_tail.csv")
        st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.caption("无订单记录。")
    with tail_tabs[2]:
        df = read_csv("reports/operations/daily_equity_tail.csv")
        st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.caption("无权益曲线记录。")

    st.markdown("### V3.0 运行按钮")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        run_button("Paper健康检查", "run_paper_health_check.py")
    with c2:
        run_button("信号命中率报告", "run_signal_hit_rate_report.py")
    with c3:
        run_button("生成运营日报", "run_daily_operations_report.py")
    with c4:
        run_button("生成V3.0总报告", "build_v30_operations_report.py")

    report_html = resolve_path("reports/v3_0_operations_report/v3_0_operations_report.html")
    st.markdown("### 报告文件")
    if report_html.exists():
        st.success(f"已生成：{report_html}")
    else:
        st.caption("尚未生成 V3.0 总报告。")

elif page == "策略研究":
    st.title("策略研究与稳健性分析")

    files = {
        "策略库汇总": "reports/strategy_library/strategy_library_summary.csv",
        "参数搜索汇总": "reports/robustness/parameter_search/strategy_parameter_search_summary.csv",
        "组合策略汇总": "reports/ensemble/ensemble_summary.csv",
        "动态仓位网格": "reports/dynamic_positioning/dynamic_position_grid.csv",
        "模型库汇总": "reports/model_library/model_library_summary.csv",
    }
    tabs = st.tabs(list(files.keys()))
    for tab, (name, path) in zip(tabs, files.items()):
        with tab:
            df = read_csv(path)
            if df.empty:
                st.warning(f"尚未生成：{path}")
            else:
                st.dataframe(df, use_container_width=True)

    st.markdown("### 研究脚本")
    c1, c2, c3 = st.columns(3)
    with c1:
        run_button("策略库回测", "run_strategy_library_backtest.py")
    with c2:
        run_button("参数稳健性搜索", "run_strategy_parameter_search.py")
    with c3:
        run_button("组合策略回测", "run_ensemble_strategy.py")

elif page == "模拟盘":
    st.title("本地模拟盘")
    paper_cfg = cfg.get("paper", {})
    db_path = resolve_path(paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))

    st.markdown("### 模拟盘数据库")
    st.write(str(db_path))
    table_counts = sqlite_table_counts(db_path)
    if table_counts.empty:
        st.warning("模拟盘数据库尚未初始化。")
    else:
        st.dataframe(table_counts, use_container_width=True, hide_index=True)

    for table in ["account_state", "target_exposure_decisions", "orders", "equity_curve", "execution_events"]:
        with st.expander(f"查看表：{table}"):
            df = latest_sqlite_table(db_path, table, limit=200)
            if df.empty:
                st.caption("无数据或表不存在。")
            else:
                st.dataframe(df, use_container_width=True)
                if table == "equity_curve":
                    cols = [c for c in ["equity", "cash"] if c in df.columns]
                    if cols:
                        st.line_chart(df[cols])

    st.markdown("### 模拟盘操作")
    replay_bars = st.number_input("回放K线数", min_value=50, max_value=5000, value=300, step=50)
    replay_reset = st.checkbox("重置后回放", value=True)
    replay_args = ["--bars", str(int(replay_bars))]
    if replay_reset:
        replay_args.append("--reset")
    c1, c2, c3 = st.columns(3)
    with c1:
        run_button("初始化模拟盘", "paper_init.py", ["--reset"], artifacts=[("模拟盘数据库", db_path)])
    with c2:
        run_button(
            "回放组合模拟盘",
            "paper_ensemble_replay_dataset.py",
            replay_args,
            key="paper_replay_dataset",
            artifacts=[("模拟盘数据库", db_path)],
        )
    with c3:
        run_button("导出组合模拟盘诊断", "run_paper_ensemble_diagnostics.py")
    run_button("组合策略预览", "paper_ensemble_preview.py", artifacts=[("组合模拟盘报告", "reports/ensemble_paper/ensemble_paper_preview.csv")])

elif page == "风控与只读影子":
    st.title("风控、安全总闸与只读影子监控")
    st.warning("本页面只做检查与报告展示，不提供真实下单入口。")

    paths = {
        "Live Gate": "reports/live_safety/live_gate_report.json",
        "Hard Circuit": "reports/live_safety/hard_circuit_report.json",
        "V2 Live Readiness": "reports/live_safety/v2_live_readiness_report.json",
        "Shadow Drift": "reports/shadow_monitor/shadow_drift_report.json",
        "Prelive Review": "reports/prelive_operator/prelive_operator_review.json",
        "API Permission Audit": "reports/prelive_operator/api_permission_audit.json",
    }
    for name, path in paths.items():
        with st.expander(name, expanded=False):
            obj = read_json(path)
            if obj is None:
                st.caption(f"尚未生成：{path}")
            else:
                st.json(obj)

    st.markdown("### 安全检查脚本")
    c1, c2, c3 = st.columns(3)
    with c1:
        run_button("部署健康检查", "deploy_check.py")
    with c2:
        run_button("状态面板快照", "status_panel.py")
    with c3:
        run_button("影子漂移检查", "shadow_drift_check.py")
    run_button("生成实盘前操作台", "prelive_operator_console.py")

elif page == "流程中心":
    st.title("流程中心")
    groups = _workflow_groups()
    tabs = st.tabs(list(groups.keys()) + ["安全流水线", "运行记录"])
    for idx, (name, steps) in enumerate(groups.items()):
        with tabs[idx]:
            render_workflow(name, steps, f"workflow_{idx}")

    with tabs[-2]:
        include_download = st.toggle("包含联网下载", value=False)
        continue_on_error = st.toggle("出错后继续", value=False)
        pipeline_args = []
        if include_download:
            pipeline_args.append("--include-download")
        if continue_on_error:
            pipeline_args.append("--continue-on-error")
        run_button(
            "运行安全研究流水线",
            "run_safe_research_pipeline.py",
            pipeline_args,
            key="safe_research_pipeline",
            artifacts=[
                ("训练数据集", cfg.get("data", {}).get("dataset_path", "data/processed/OKX_BTC_USDT_SWAP_4h_dataset.parquet")),
                ("模型文件", cfg.get("model", {}).get("model_path", "models/btc_direction_model.joblib")),
                ("准入摘要", "reports/model_admission/model_strategy_admission_summary.json"),
                ("运营摘要", "reports/operations/daily_operations_summary.json"),
            ],
            timeout_seconds=3600,
        )

    with tabs[-1]:
        run_history_panel()

elif page == "软件审查":
    st.title("软件包审查")
    st.markdown("### 核心功能覆盖")
    coverage = pd.DataFrame([
        {"模块": "数据", "状态": "已具备", "说明": "CCXT公开行情下载、Parquet存储、增量更新接口"},
        {"模块": "特征", "状态": "已具备", "说明": "收益率、趋势、波动率、成交量、K线结构、RSI"},
        {"模块": "模型", "状态": "已具备", "说明": "ExtraTrees、RF、Logistic、HGB等，支持时间切分和walk-forward"},
        {"模块": "策略", "状态": "已具备", "说明": "趋势、突破、均值回归、波动压缩、组合策略"},
        {"模块": "回测", "状态": "已具备", "说明": "固定杠杆与动态target_exposure回测"},
        {"模块": "模拟盘", "状态": "已具备", "说明": "SQLite状态化模拟盘、组合策略动态调仓"},
        {"模块": "Demo/Testnet", "状态": "已具备但默认关闭", "说明": "订单意图、保护单、对账、幂等、状态机"},
        {"模块": "实盘", "状态": "明确不开放", "说明": "仅保留只读影子检查、安全总闸和人工审核"},
        {"模块": "前端", "状态": "V2.3新增", "说明": "Streamlit研究控制台，聚合报告、按钮、图表和安全状态"},
        {"模块": "数据质量", "状态": "V2.4新增", "说明": "缺失K线、重复时间戳、OHLC一致性、极端跳价、异常成交量检测"},
        {"模块": "回测真实性", "状态": "V2.4新增", "说明": "资金费率、强平缓冲区、成本与杠杆风险报告"},
        {"模块": "严格验证", "状态": "V2.4新增", "说明": "Purged / Embargo 时间序列交叉验证，降低标签泄露风险"},
        {"模块": "概率校准", "状态": "V2.5新增", "说明": "Isotonic/Sigmoid 后验概率校准，输出 Brier/ECE/MCE 与可靠性曲线"},
        {"模块": "信号可信度", "状态": "V2.5新增", "说明": "weak/medium/strong 信号分层，并映射到动态 target_exposure"},
        {"模块": "Walk-forward校准", "状态": "V2.6新增", "说明": "每个fold独立训练、校准、测试，避免校准器对测试窗口泄露"},
        {"模块": "模型库增强", "状态": "V2.7新增", "说明": "LightGBM/XGBoost 可选后端、模型可用性检查、增强模型库与walk-forward校准模型对比"},
        {"模块": "序列模型实验", "状态": "V2.8新增", "说明": "sequence_mlp、可选LSTM/GRU/TCN、固定切分和walk-forward序列实验"},
        {"模块": "统一排行榜与准入", "状态": "V2.9新增", "说明": "统一排序表格模型、校准模型、序列模型、规则策略和组合策略，并分配准入等级"},
        {"模块": "运营日报", "状态": "V3.0新增", "说明": "模拟盘权益/回撤、准入池变化、概率漂移、滚动命中率和策略失效提醒"},
    ])
    st.dataframe(coverage, use_container_width=True, hide_index=True)

    st.markdown("### 需要继续改进的方向")
    improvements = pd.DataFrame([
        {"优先级": "已完成", "方向": "数据质量", "建议": "V2.4 已加入缺失K线、异常成交量、极端跳价和OHLC一致性检测。"},
        {"优先级": "已完成", "方向": "模型评估", "建议": "V2.4 已加入 Purged/Embargo 时间序列交叉验证；V2.5 已加入概率校准与信号可信度分层。"},
        {"优先级": "已完成", "方向": "执行仿真", "建议": "V2.4 已加入资金费率、强平缓冲和真实性报告；后续可细化交易所逐档费率。"},
        {"优先级": "中", "方向": "前端", "建议": "后续可把Streamlit升级为FastAPI + React，但当前研究阶段Streamlit更高效。"},
        {"优先级": "已完成", "方向": "模型库增强", "建议": "V2.7 已加入 LightGBM/XGBoost 可选依赖和多模型 walk-forward 校准对比。"},
        {"优先级": "已完成", "方向": "概率校准", "建议": "V2.6 已加入 walk-forward train/calibration/test 校准流程，用于替代固定切分的单次校准。"},
        {"优先级": "中", "方向": "资金管理", "建议": "增加Kelly上限、波动率目标与最大连续亏损降杠杆的联动。"},
        {"优先级": "已完成", "方向": "候选筛选", "建议": "V2.9 已加入统一模型/策略排行榜和paper候选准入门槛。"},
        {"优先级": "已完成", "方向": "长期模拟盘运营", "建议": "V3.0 已加入运营日报、paper健康检查、信号命中率、概率漂移和准入状态变化跟踪。"},
    ])
    st.dataframe(improvements, use_container_width=True, hide_index=True)

    st.markdown("### 文件状态")
    show_file_table()
