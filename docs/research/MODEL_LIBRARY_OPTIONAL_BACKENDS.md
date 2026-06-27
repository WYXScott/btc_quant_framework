# V2.7 Optional Model Backends

V2.7 adds optional LightGBM and XGBoost model candidates while keeping the default package runnable with only the base `requirements.txt`.

## Why optional?

The BTC low-frequency research framework should remain easy to install and reproducible.  ExtraTrees, RandomForest, Logistic Regression, HistGradientBoosting and GradientBoosting are still the default built-in model family.  LightGBM and XGBoost can be stronger on tabular features, but they add binary dependencies and can be harder to install on some systems.

## Install optional backends

```bash
pip install -r requirements-optional.txt
```

Then verify:

```bash
python scripts/check_model_backends.py
```

## Run enhanced model library

```bash
python scripts/run_enhanced_model_library.py
```

Unavailable optional models are skipped cleanly and recorded in:

```text
reports/enhanced_model_library/model_availability.csv
reports/enhanced_model_library/skipped_models.csv
```

## Run walk-forward calibrated model comparison

```bash
python scripts/run_wf_calibration_model_library.py
```

This compares available models under the strict train → calibration → test rolling workflow.  It is the preferred comparison before using model probabilities for target exposure.

## Safety note

V2.7 does not open live trading.  All model comparison scripts are research-only.
