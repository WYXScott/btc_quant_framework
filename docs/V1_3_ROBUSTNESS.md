# V1.3 Robustness and Hyperparameter Search

V1.3 adds coarse hyperparameter search and robustness diagnostics for BTC low-frequency leveraged research.

## Main scripts

```bash
python scripts/run_strategy_parameter_search.py
python scripts/run_top_candidate_robustness.py
python scripts/run_ml_threshold_grid.py
python scripts/build_v13_research_report.py
```

## What to inspect

- `reports/robustness/parameter_search/strategy_parameter_search_summary.csv`
- `reports/robustness/top_candidate/segments.csv`
- `reports/robustness/top_candidate/regimes.csv`
- `reports/robustness/top_candidate/cost_slippage_stress.csv`
- `reports/robustness/top_candidate/leverage_boundary.csv`
- `reports/robustness/ml_threshold_grid/ml_threshold_grid_summary.csv`
- `reports/v1_3_research_report/v1_3_research_report.html`

## Reading the ranking

`robust_rank_score` is a research heuristic. It rewards Calmar, Sharpe, positive segment coverage, cost-stress retention, and sufficient trade count. It penalizes large drawdowns and high `overfit_risk_score`.

Do not treat this as proof of profitability. A candidate should remain paper/demo only unless it survives out-of-sample testing, demo execution, cost stress, and leverage boundary checks.

## Leverage note

For a 1000 USDT account, 10x leverage should be treated as stress-testing, not as the default deployment setting. Prefer 3x until the system has a long simulated and Demo/Testnet record.
