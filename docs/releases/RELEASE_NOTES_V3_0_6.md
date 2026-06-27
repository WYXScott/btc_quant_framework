# BTC Quant Framework V3.0.6

V3.0.6 improves the Streamlit user experience and reduces reliance on manual command-line execution.

## Added

- Streamlit **流程中心** page with staged workflow groups:
  - 基础构建
  - 研究评估
  - 模拟运营
  - 实时行情
- Per-step status tables based on expected output artifacts.
- One-button selected-step runner with command output and artifact status display.
- Session run history for recent UI-triggered scripts.
- Homepage quick actions for realtime sampling, data quality, daily operations and safety checks.
- UI controls for realtime sample message count.
- UI controls for paper replay bar count and reset mode.

## Changed

- Replaced the older long **一键流程** button list with a stage-oriented workflow center.
- Added `paper_ensemble_replay_dataset.py` to the UI safe-mode script whitelist.

## Safety

- UI actions still route through `ui.allowed_button_scripts`.
- No live order submission buttons are added.
- Realtime and paper-trading controls remain public-data/local-simulation only.
