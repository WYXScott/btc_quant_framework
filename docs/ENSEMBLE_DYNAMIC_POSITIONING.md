# V1.4 组合式策略集成与动态仓位管理

V1.4 的目标是把 V1.3 中筛选出的稳健策略候选进一步组合，形成一个可诊断、可回测的多策略集成框架。

## 核心思想

1. 从 `strategy_parameter_search_summary.csv` 中选择稳健候选策略；
2. 根据 `robust_rank_score` 和 `overfit_risk_score` 生成保守权重；
3. 将多个策略的 0/1 信号合成为 `ensemble_score`；
4. 通过投票阈值生成组合信号；
5. 根据波动率目标、市场状态和信号强度生成 `target_exposure`；
6. 使用 `DynamicExposureBacktester` 回测动态名义敞口。

## 推荐运行顺序

```bash
python scripts/download_ohlcv.py
python scripts/build_features.py
python scripts/run_strategy_parameter_search.py
python scripts/run_ensemble_strategy.py
python scripts/run_dynamic_position_grid.py
python scripts/run_strategy_failure_check.py
python scripts/build_v14_research_report.py
```

## 关键输出

```text
reports/ensemble/ensemble_candidates.csv
reports/ensemble/ensemble_signal_exposure.csv
reports/ensemble/ensemble_dynamic_backtest_result.csv
reports/ensemble/ensemble_summary.csv
reports/ensemble/strategy_failure_status.csv
reports/dynamic_positioning/dynamic_position_grid.csv
reports/v1_4_research_report/v1_4_research_report.html
```

## target_exposure 含义

`target_exposure = 1.0` 表示 1 倍名义敞口；`target_exposure = 3.0` 表示 3 倍名义敞口。它不是保证金比例，而是账户权益对应的名义风险暴露倍数。

## 风险边界

V1.4 仍然不是实盘系统。动态仓位可能在回测中降低波动，但不代表真实交易中一定能降低风险。真实交易还需要考虑：

- 交易所强平公式；
- 标记价格与成交价格差异；
- 极端滑点；
- 止损单触发失败；
- API 延迟与断线；
- 流动性不足；
- 手续费等级变化。

对于 1000 USDT、3–10 倍杠杆账户，建议默认 `max_exposure <= 3.0`，并优先验证 3 倍配置。
