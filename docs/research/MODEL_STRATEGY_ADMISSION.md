# V2.9 统一模型排行榜与策略准入标准

V2.9 的目标是解决研究阶段的一个实际问题：系统里已经有表格模型、可选 LightGBM/XGBoost、walk-forward 校准模型、序列模型、规则策略、组合策略，但如果没有统一准入标准，很容易出现“模型越来越多，但不知道哪个该进入模拟盘”的问题。

## 1. 输入来源

`run_model_strategy_admission.py` 会自动读取以下报告，缺失文件会被跳过：

- `reports/enhanced_model_library/model_library_summary.csv`
- `reports/walk_forward_calibration_model_library/walk_forward_calibration_model_library_summary.csv`
- `reports/walk_forward_calibration/walk_forward_calibration_summary.json`
- `reports/sequence_models/sequence_model_summary.csv`
- `reports/sequence_walk_forward/sequence_walk_forward_summary.csv`
- `reports/robustness/parameter_search/strategy_parameter_search_summary.csv`
- `reports/ensemble/ensemble_summary.csv`
- `reports/calibrated_ml_backtest/calibrated_ml_summary.csv`

## 2. 输出文件

```bash
python scripts/run_model_strategy_admission.py
```

输出目录：

```text
reports/model_admission/
```

核心文件：

- `candidate_universe.csv`：所有候选模型/策略的统一格式表。
- `model_strategy_leaderboard.csv`：带准入分数和决策的排行榜。
- `admission_summary.csv`：准入类别统计。
- `model_strategy_admission_summary.json`：摘要与阈值配置。
- `model_strategy_admission_report.html`：HTML 报告。
- `leaderboard_top_scores.png`：Top 候选分数图。

## 3. 准入等级

| 等级 | 含义 |
|---|---|
| `paper_candidate_pool` | 允许进入本地模拟盘候选池，但不代表可以实盘。 |
| `watchlist` | 观察名单，需要更多 walk-forward、校准或长期模拟盘证据。 |
| `research_only` | 仅保留为研究观察，不建议接入模拟盘。 |
| `rejected` | 当前证据不足、风险过高或状态异常，应淘汰。 |

## 4. 为什么固定切分和序列模型会被保守处理

固定切分结果容易受单一时间窗口影响；序列模型尤其容易过拟合。因此 V2.9 会对以下候选自动设置分数上限：

- `tabular_model_fixed_split`
- `sequence_model_fixed_split`
- `sequence_model_walk_forward`

这不是说这些模型没价值，而是要求它们先在 walk-forward 校准、长期模拟盘和回测真实性报告中证明稳定性。

## 5. 前端入口

启动前端：

```bash
python scripts/run_dashboard.py
```

打开页面：

```text
统一排行榜与准入
```

前端可查看候选总数、准入类别、排行榜、候选宇宙和 HTML 报告。

## 6. 安全边界

V2.9 的准入结果只用于研究和本地模拟盘候选筛选：

- 不开放真实下单；
- 不改变 live trading 总闸；
- 不覆盖 kill switch；
- 不代表投资建议；
- 不代表策略可盈利。

进入任何小资金真实验证之前，仍需通过 V2.0–V2.2 的只读影子实盘、人工 checklist、hard circuit、pre-live review，以及至少 30 天 Demo/模拟盘验证。
