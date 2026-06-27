# V1.2 Strategy and Model Library

V1.2 expands the project from a single BTC ML signal into a research framework for comparing candidate strategy and model families.

## Strategy library

Run:

```bash
python scripts/run_strategy_library_backtest.py
```

Included strategy candidates:

- `buy_and_hold`: passive BTC long benchmark.
- `ma_trend`: MA24/MA120 trend filter.
- `donchian_breakout`: breakout above prior high, exit on prior low breakdown.
- `vol_squeeze_breakout`: volatility compression followed by upside breakout.
- `rsi_mean_reversion`: oversold rebound strategy with trend filter.
- `regime_filtered_trend`: trend signal gated by volatility and candle-strength features.

Primary output:

```text
reports/strategy_library/strategy_library_summary.csv
```

## Model library

Run:

```bash
python scripts/run_model_library_diagnostics.py
```

Included model candidates:

- `extra_trees`
- `random_forest`
- `logistic_l2`
- `hist_gradient_boosting`
- `gradient_boosting`

Primary output:

```text
reports/model_library/model_library_summary.csv
```

The linear model is not expected to be the best model. It is a baseline. If tree/boosting models do not clearly improve over the linear baseline in validation/test splits, the nonlinear signal is probably weak or overfit.

## Model-strategy matrix

Run:

```bash
python scripts/run_model_strategy_matrix.py
```

This walk-forwards each configured model, converts its probability output into the same ML trading rule, then backtests with the configured BTC leverage/cost assumptions.

Primary output:

```text
reports/model_strategy_matrix/model_strategy_matrix_summary.csv
```

## Report

After running the three scripts above:

```bash
python scripts/build_v12_research_report.py
```

Primary output:

```text
reports/v1_2_research_report/v1_2_research_report.html
```

## Interpretation rules

Prefer candidates that show:

- acceptable drawdown under 3x leverage before testing 5x or 10x;
- enough trades to be statistically meaningful;
- stable walk-forward fold metrics;
- no dependence on one short market regime;
- lower turnover after fees and slippage;
- sensible behavior relative to the buy-and-hold benchmark.

This module is still for research and Demo/Testnet preparation only. It does not authorize live trading.
