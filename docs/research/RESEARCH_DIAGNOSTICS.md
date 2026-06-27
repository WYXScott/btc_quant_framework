# V1.1 Research Diagnostics

This module is designed to answer a practical question before any real-money trading:

> Is the BTC-only low-frequency strategy statistically and operationally credible enough to keep testing?

## Added scripts

```bash
python scripts/run_model_diagnostics.py
python scripts/run_strategy_diagnostics.py
python scripts/run_leverage_risk_report.py
python scripts/build_research_report.py
```

## What to inspect

1. `model_metrics.json`  
   Check ROC-AUC, Brier score, precision, recall, and log loss. A high accuracy alone is not enough.

2. `calibration_table.csv`  
   The predicted probability buckets should broadly align with the actual positive rate. If the model predicts 0.65 but the actual positive rate is near 0.50, probability thresholds are unreliable.

3. `feature_importance.csv`  
   Confirm that the model is using plausible market features rather than accidental columns.

4. `regime_performance.csv`  
   Check whether the strategy only works in one regime, such as BTC above MA120 with low volatility.

5. `drawdown_events.csv`  
   Examine the worst drawdown windows. These periods are where leverage usually fails.

6. `leverage_risk_table.csv`  
   Prefer robust 3x behavior. Treat 10x as a stress scenario, not a default deployment choice.

## Decision rule before demo/live

Do not move toward exchange-demo execution unless:

- walk-forward results are acceptable;
- model calibration is not obviously misleading;
- drawdown events are survivable at 3x;
- the strategy does not rely on one narrow historical regime;
- paper trading runs for a meaningful period without state, order, or reconciliation errors.
