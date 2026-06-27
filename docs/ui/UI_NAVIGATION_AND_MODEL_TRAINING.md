# UI Navigation And Model Training Guide

V3.2.0 reorganizes the Streamlit console around user intent instead of exposing every script as a flat menu.

## Navigation model

The sidebar now has two levels:

1. **工作模式**: choose the current operating context.
2. **页面**: choose one of the pages relevant to that context.

Available modes:

| Mode | Purpose |
|---|---|
| 新手模式 | Minimal entry points for the first full local run. |
| 研究验证 | Model training, calibration, walk-forward validation, admission, and strategy research. |
| 运行监控 | Realtime market data, managed services, paper trading, operations, and safety monitoring. |
| 高级工具箱 | Lower-level or legacy pages retained for debugging and extensions. |

This keeps the existing functionality available while reducing the number of choices shown to a new user.

## Recommended starting path

Use the **开始使用** page first. It shows:

- current dataset/model/realtime/paper readiness;
- a recommended next step based on missing artifacts;
- the four-stage route: data preparation, model training, robust validation, and simulated operations;
- a status table for the starter workflow.

The page is intended to answer: **what should I do next?**

## Model training workflow

Use **模型训练向导** for all model-training work. The workflow is intentionally ordered:

1. **下载/更新OKX 4H K线**  
   Produces the raw OHLCV parquet file.

2. **检查K线质量**  
   Produces the data-quality report. Critical failures block feature generation and model training.

3. **构建特征与未来收益标签**  
   Produces feature and dataset parquet files.

4. **训练基础方向模型**  
   Produces the base model and the feature-column list.

5. **生成模型诊断**  
   Reviews fixed-split performance and feature behavior.

6. **训练校准模型**  
   Calibrates probabilities so signal confidence is easier to interpret.

7. **生成信号可信度报告**  
   Converts calibrated probabilities into weak/medium/strong confidence tiers.

8. **运行Walk-forward校准验证**  
   Uses rolling train/calibration/test windows for more realistic out-of-sample validation.

9. **生成模型/策略准入排行榜**  
   Summarizes model and strategy candidates for admission decisions.

## How to interpret model results

Do not judge the system by a single fixed-split AUC or one backtest curve.

Prefer this order:

1. Data quality report has no critical failure.
2. Fixed-split diagnostic is reasonable.
3. Calibration improves or at least does not damage probability reliability.
4. Walk-forward metrics remain stable across folds.
5. Admission leaderboard does not rely on excessive drawdown, leverage, or a single lucky period.
6. Paper-trading replay and local paper loop behave consistently.

## Advanced pages

The old dense pages are not removed. They are available under **高级工具箱** for debugging and extension work.

The recommended day-to-day entry points are now:

- **开始使用** for next-step guidance;
- **模型训练向导** for model work;
- **服务控制台** for long-running local services;
- **运营日报** for paper-trading review;
- **软件审查** for stability and package review.
