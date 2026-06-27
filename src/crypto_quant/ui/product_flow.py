from __future__ import annotations

from typing import Any


PAGE_GROUPS: dict[str, list[str]] = {
    "新手模式": [
        "开始使用",
        "模型训练向导",
        "实时行情",
        "模拟盘",
    ],
    "研究验证": [
        "模型训练向导",
        "数据质量与真实性",
        "概率校准与信号可信度",
        "Walk-forward校准",
        "统一排行榜与准入",
        "策略研究",
    ],
    "运行监控": [
        "系统总览",
        "服务控制台",
        "实时行情",
        "模拟盘",
        "运营日报",
        "风控与只读影子",
    ],
    "高级工具箱": [
        "数据与模型（高级）",
        "模型库增强",
        "序列模型实验",
        "流程中心",
        "软件审查",
    ],
}

PAGE_ALIASES: dict[str, str] = {
    "系统总览": "总览",
    "数据与模型（高级）": "数据与模型",
}

MODE_DESCRIPTIONS: dict[str, str] = {
    "新手模式": "只保留最常用入口，适合从零开始跑通数据、模型和模拟盘。",
    "研究验证": "围绕训练、校准、walk-forward、准入和策略研究组织。",
    "运行监控": "围绕实时行情、本地服务、模拟盘和运营日报组织。",
    "高级工具箱": "保留完整底层工具，适合排查和扩展。",
}


def normalize_page(display_page: str) -> str:
    return PAGE_ALIASES.get(display_page, display_page)


def model_training_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    data_cfg = cfg.get("data", {}) or {}
    model_cfg = cfg.get("model", {}) or {}
    calibration_cfg = cfg.get("calibration", {}) or {}
    model_admission_cfg = cfg.get("model_admission", {}) or {}
    admission_output = model_admission_cfg.get("output_path", "reports/model_admission")
    return [
        {
            "stage": "数据准备",
            "label": "下载/更新OKX 4H K线",
            "short_label": "下载K线",
            "script": "download_ohlcv.py",
            "why": "获取训练所需的公开历史行情。不会读取私钥，也不会下单。",
            "outputs": [("原始K线", data_cfg.get("raw_path", "data/raw/OKX_BTC_USDT_SWAP_4h.parquet"))],
        },
        {
            "stage": "数据准备",
            "label": "检查K线质量",
            "short_label": "质量检查",
            "script": "run_data_quality_check.py",
            "why": "确认缺口、重复时间戳、异常OHLC等问题；失败时阻断后续训练。",
            "outputs": [("数据质量报告", "reports/data_quality/data_quality_report.json")],
        },
        {
            "stage": "特征与标签",
            "label": "构建特征与未来收益标签",
            "short_label": "构建数据集",
            "script": "build_features.py",
            "why": "把K线转换成技术指标、未来收益和方向标签，形成训练集。",
            "outputs": [
                ("特征数据", data_cfg.get("feature_path", "data/processed/OKX_BTC_USDT_SWAP_4h_features.parquet")),
                ("训练数据集", data_cfg.get("dataset_path", "data/processed/OKX_BTC_USDT_SWAP_4h_dataset.parquet")),
            ],
        },
        {
            "stage": "基础模型",
            "label": "训练基础方向模型",
            "short_label": "训练模型",
            "script": "train_model.py",
            "why": "训练BTC未来约24小时方向分类模型，并输出模型文件和特征列表。",
            "outputs": [
                ("模型文件", model_cfg.get("model_path", "models/btc_direction_model.joblib")),
                ("特征列表", model_cfg.get("feature_list_path", "models/btc_feature_columns.txt")),
            ],
        },
        {
            "stage": "基础模型",
            "label": "生成模型诊断",
            "short_label": "模型诊断",
            "script": "run_model_diagnostics.py",
            "why": "查看模型样本外表现、重要特征和潜在过拟合风险。",
            "outputs": [("模型诊断", "reports/model_diagnostics/model_diagnostics_summary.json")],
        },
        {
            "stage": "概率校准",
            "label": "训练校准模型",
            "short_label": "概率校准",
            "script": "train_calibrated_model.py",
            "why": "把原始分类概率校准为更可解释的交易信号置信度。",
            "outputs": [
                ("校准模型", calibration_cfg.get("calibrated_model_path", "models/btc_direction_model_calibrated.joblib")),
                ("校准指标", "reports/calibration/calibration_metrics.json"),
            ],
        },
        {
            "stage": "概率校准",
            "label": "生成信号可信度报告",
            "short_label": "信号分层",
            "script": "run_signal_confidence_report.py",
            "why": "把校准概率映射为弱/中/强信号和目标敞口，便于后续回测与模拟盘。",
            "outputs": [("信号分层", "reports/signal_confidence/confidence_tier_table.csv")],
        },
        {
            "stage": "样本外验证",
            "label": "运行Walk-forward校准验证",
            "short_label": "WF验证",
            "script": "run_walk_forward_calibration.py",
            "why": "使用滚动训练/校准/测试窗口检查模型是否在样本外稳定。",
            "outputs": [("WF校准摘要", "reports/walk_forward_calibration/walk_forward_calibration_summary.json")],
        },
        {
            "stage": "准入判断",
            "label": "生成模型/策略准入排行榜",
            "short_label": "准入排行",
            "script": "run_model_strategy_admission.py",
            "why": "把模型、策略、回撤和稳定性指标放在同一张排行榜里，避免只看单次AUC。",
            "outputs": [
                ("准入摘要", f"{admission_output}/model_strategy_admission_summary.json"),
                ("排行榜", f"{admission_output}/model_strategy_leaderboard.csv"),
            ],
        },
    ]


def starter_flow_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    paper_cfg = cfg.get("paper", {}) or {}
    ops_cfg = cfg.get("operations", {}) or {}
    realtime_cfg = cfg.get("realtime", {}) or {}
    return [
        *model_training_steps(cfg)[:5],
        {
            "stage": "模拟运营",
            "label": "初始化本地模拟盘",
            "short_label": "初始化Paper",
            "script": "paper_init.py",
            "args": ["--reset"],
            "why": "创建本地SQLite模拟盘账本，不连接交易所下单。",
            "outputs": [("模拟盘数据库", paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))],
        },
        {
            "stage": "模拟运营",
            "label": "回放组合模拟盘",
            "short_label": "Paper回放",
            "script": "paper_ensemble_replay_dataset.py",
            "args": ["--bars", "300", "--reset"],
            "why": "用历史数据回放本地组合策略，检查信号到账本的完整链路。",
            "outputs": [("模拟盘数据库", paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))],
        },
        {
            "stage": "运行监控",
            "label": "采样OKX实时行情",
            "short_label": "实时采样",
            "script": "run_okx_realtime_listener.py",
            "args": ["--max-messages", "5"],
            "why": "验证OKX公共WebSocket连接和本地SQLite写入。",
            "outputs": [("实时数据库", realtime_cfg.get("database_path", "data/database/realtime_market.sqlite"))],
        },
        {
            "stage": "运行监控",
            "label": "生成运营日报",
            "short_label": "运营日报",
            "script": "run_daily_operations_report.py",
            "why": "汇总模拟盘、信号命中率和运行状态，形成日常复盘入口。",
            "outputs": [("运营摘要", f"{ops_cfg.get('output_path', 'reports/operations')}/daily_operations_summary.json")],
        },
    ]
