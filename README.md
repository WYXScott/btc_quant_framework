# BTC Quant Framework V2.8

这是一个面向 **BTC/USDT 低频杠杆交易研究、回测、模拟盘与只读影子监控** 的 Python 工程框架。

V2.8 的重点是：**序列模型实验层**。它在 V2.7 的模型库增强基础上，新增固定窗口序列数据构造、sequence_mlp 基线、可选 PyTorch LSTM/GRU/TCN，以及序列模型 walk-forward 对比。

> 当前版本不开放实盘自动交易。真实账户相关功能仅限只读影子检查、安全总闸、Kill Switch 和人工审核流程。

---

## 1. 快速启动

```bash
cd btc_quant_framework_v2_8
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/run_dashboard.py
```

也可以直接运行：

```bash
streamlit run frontend/app.py
```

---

## 2. 可选模型后端

核心环境不需要 LightGBM/XGBoost。需要时再安装：

```bash
pip install -r requirements-optional.txt
python scripts/check_model_backends.py
```

未安装可选包时，相关模型会被跳过，不影响默认研究流程。

---


## 2.1 序列模型实验

默认不需要 PyTorch，仅运行内置 `sequence_mlp`：

```bash
python scripts/check_sequence_model_backends.py
python scripts/run_sequence_model_experiments.py
python scripts/run_sequence_walk_forward.py
python scripts/build_v28_sequence_report.py
```

如果要实验 LSTM / GRU / TCN，再安装可选依赖：

```bash
pip install -r requirements-sequence.txt
```

序列模型结果仅用于研究报告，不直接接入模拟盘或实盘执行。

## 3. 推荐研究流程

```bash
python scripts/download_ohlcv.py
python scripts/run_data_quality_check.py
python scripts/build_features.py
python scripts/train_model.py
python scripts/run_model_diagnostics.py
python scripts/train_calibrated_model.py
python scripts/run_signal_confidence_report.py
python scripts/run_calibrated_ml_backtest.py
python scripts/run_walk_forward_calibration.py
python scripts/check_model_backends.py
python scripts/run_enhanced_model_library.py
python scripts/run_wf_calibration_model_library.py
python scripts/build_v27_research_report.py
python scripts/check_sequence_model_backends.py
python scripts/run_sequence_model_experiments.py
python scripts/run_sequence_walk_forward.py
python scripts/build_v28_sequence_report.py
python scripts/run_purged_embargo_cv.py
python scripts/run_strategy_parameter_search.py
python scripts/run_ensemble_strategy.py
python scripts/audit_package.py
```

也可以：

```bash
python scripts/run_safe_research_pipeline.py --include-download
```

---

## 4. 关键报告

```text
reports/model_backends/model_backend_availability.csv
reports/enhanced_model_library/enhanced_model_library_report.html
reports/walk_forward_calibration_model_library/walk_forward_calibration_model_library_report.html
reports/v2_7_research_report/v2_7_research_report.html
```

---

## 5. 安全边界

- 不开放真实自动下单。
- 前端没有实盘下单按钮。
- Demo/Testnet 相关执行仍默认 dry-run。
- Live Gate 默认阻断真实交易。

## V2.9 统一模型排行榜与策略准入

V2.9 新增统一模型/策略准入层，用于汇总表格模型、可选 LightGBM/XGBoost、walk-forward 校准模型、序列模型、规则策略和组合策略，并输出：

```bash
python scripts/run_model_strategy_admission.py
python scripts/build_v29_admission_report.py
```

主要报告：

```text
reports/model_admission/model_strategy_leaderboard.csv
reports/model_admission/model_strategy_admission_report.html
reports/v2_9_admission_report/v2_9_admission_report.html
```

准入等级只用于本地模拟盘候选筛选，不开放实盘自动交易。

## V3.0 模拟盘长期运行与自动研究日报

V3.0 新增运营日报层，用于长期模拟盘和研究运维：

```bash
python scripts/run_paper_health_check.py
python scripts/run_signal_hit_rate_report.py
python scripts/run_daily_operations_report.py
python scripts/build_v30_operations_report.py
```

主要报告：

```text
reports/operations/daily_operations_report.html
reports/v3_0_operations_report/v3_0_operations_report.html
```

前端新增 **运营日报** 页面：

```bash
python scripts/run_dashboard.py
```

该版本仍然不开放真实自动交易。
