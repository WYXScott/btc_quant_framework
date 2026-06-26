from __future__ import annotations

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
    border-radius: 18px;
    padding: 1rem 1.1rem;
    background: linear-gradient(135deg, rgba(255,255,255,.08), rgba(255,255,255,.02));
    box-shadow: 0 6px 20px rgba(0,0,0,.06);
}
.small-note {font-size: .88rem; color: #777;}
.good {color: #0a8f48; font-weight: 700;}
.warn {color: #b7791f; font-weight: 700;}
.bad {color: #c53030; font-weight: 700;}
code {border-radius: 8px;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

cfg = load_yaml()

st.sidebar.title("₿ BTC Quant Console")
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
        "一键流程",
        "软件审查",
    ],
)

st.sidebar.markdown("---")
st.sidebar.caption("默认只展示研究、回测、模拟盘和安全检查功能；界面不提供真实实盘下单按钮。")


def show_file_table():
    status_df = collect_core_status(cfg)
    if not status_df.empty:
        status_df["size_kb"] = (status_df["size_bytes"] / 1024).round(1)
        st.dataframe(status_df[["path", "exists", "size_kb", "modified"]], use_container_width=True, hide_index=True)


def run_button(label: str, script: str, args: list[str] | None = None, help_text: str | None = None):
    if st.button(label, help=help_text, use_container_width=True):
        with st.spinner(f"运行 {script} ..."):
            code, out = safe_run_script(script, args)
        if code == 0:
            st.success(f"{script} 运行完成")
        else:
            st.error(f"{script} 返回码：{code}")
        st.code(out or "<no output>", language="text")


if page == "总览":
    st.title("BTC 低频杠杆量化研究控制台")
    st.caption("V3.0 Research UI：面向 BTC/USDT、4h 低频、3–10x 杠杆研究、统一模型排行榜、长期模拟盘运营日报与只读安全监控。")

    data_summary = summarize_dataset(cfg)
    model_summary = summarize_model(cfg)
    paper_db = resolve_path(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    table_counts = sqlite_table_counts(paper_db)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("数据集行数", data_summary.get("rows", 0))
    c2.metric("特征列数", data_summary.get("columns", 0))
    c3.metric("模型已训练", "是" if model_summary.get("model_exists") else "否")
    c4.metric("SQLite表数", len(table_counts) if not table_counts.empty else 0)

    st.markdown("### 当前链路状态")
    show_file_table()

    st.markdown("### 快速判断")
    checks = []
    checks.append(("原始K线数据", data_summary.get("exists", False)))
    checks.append(("训练数据集", data_summary.get("exists", False) and data_summary.get("rows", 0) > 1000))
    checks.append(("模型文件", model_summary.get("model_exists", False)))
    checks.append(("模拟盘数据库", paper_db.exists()))
    checks_df = pd.DataFrame([{"检查项": k, "状态": "通过" if v else "待完成"} for k, v in checks])
    st.dataframe(checks_df, use_container_width=True, hide_index=True)

    st.info("建议顺序：先运行数据/特征/模型训练，再运行策略研究与模拟盘回放，最后看风控与影子监控。")

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
    c1, c2, c3 = st.columns(3)
    with c1:
        run_button("采样实时行情", "run_okx_realtime_listener.py", ["--max-messages", "5"], help_text="采样接收少量公开行情消息后自动停止。")
    with c2:
        run_button("查看实时状态", "run_realtime_status.py")
    with c3:
        run_button("合并4H实时K线", "merge_realtime_ohlcv.py", help_text="仅合并已确认的4H K线。")


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
    c1, c2, c3 = st.columns(3)
    with c1:
        run_button("初始化模拟盘", "paper_init.py", ["--reset"])
    with c2:
        run_button("组合策略预览", "paper_ensemble_preview.py")
    with c3:
        run_button("导出组合模拟盘诊断", "run_paper_ensemble_diagnostics.py")

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

elif page == "一键流程":
    st.title("一键流程：研究与模拟盘")
    st.markdown(
        """
        这里提供的是**安全流程入口**，不会提交真实订单。  
        对于第一次运行，建议按从上到下顺序执行。
        """
    )
    steps = [
        ("部署健康检查", "deploy_check.py", []),
        ("下载/更新公开K线", "download_ohlcv.py", []),
        ("检查K线质量", "run_data_quality_check.py", []),
        ("构建特征与标签", "build_features.py", []),
        ("训练模型", "train_model.py", []),
        ("模型诊断", "run_model_diagnostics.py", []),
        ("训练校准模型", "train_calibrated_model.py", []),
        ("信号可信度报告", "run_signal_confidence_report.py", []),
        ("校准ML回测", "run_calibrated_ml_backtest.py", []),
        ("Walk-forward概率校准", "run_walk_forward_calibration.py", []),
        ("检查模型后端", "check_model_backends.py", []),
        ("增强模型库", "run_enhanced_model_library.py", []),
        ("WF校准模型库", "run_wf_calibration_model_library.py", []),
        ("严格CV验证", "run_purged_embargo_cv.py", []),
        ("策略参数搜索", "run_strategy_parameter_search.py", []),
        ("组合策略回测", "run_ensemble_strategy.py", []),
        ("初始化模拟盘", "paper_init.py", ["--reset"]),
        ("组合模拟盘预览", "paper_ensemble_preview.py", []),
        ("生成操作台", "prelive_operator_console.py", []),
    ]
    for label, script, args in steps:
        run_button(label, script, args)

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
