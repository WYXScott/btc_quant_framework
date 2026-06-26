# Release Notes V2.9

## BTC Quant Framework V2.9 — Unified Model & Strategy Admission

V2.9 adds a conservative admission layer that ranks all available model and strategy candidates with a unified schema.

### New modules

- `src/crypto_quant/research/model_admission.py`

### New scripts

- `scripts/run_model_strategy_admission.py`
- `scripts/build_v29_admission_report.py`
- `scripts/model_admission_smoke.py`

### New reports

- `reports/model_admission/candidate_universe.csv`
- `reports/model_admission/model_strategy_leaderboard.csv`
- `reports/model_admission/admission_summary.csv`
- `reports/model_admission/model_strategy_admission_summary.json`
- `reports/model_admission/model_strategy_admission_report.html`
- `reports/model_admission/leaderboard_top_scores.png`
- `reports/v2_9_admission_report/v2_9_admission_report.html`

### Frontend

The Streamlit dashboard now has a new page:

- `统一排行榜与准入`

### Safety boundary

V2.9 does **not** enable live trading. Admission results are for research and local paper-trading candidate selection only.
