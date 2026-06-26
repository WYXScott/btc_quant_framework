# Release Notes - V2.6

## 新增

- Walk-forward 概率校准模块 `src/crypto_quant/models/walk_forward_calibration.py`
- `run_walk_forward_calibration.py`
- `build_v26_research_report.py`
- `walk_forward_calibration_smoke.py`
- 前端新增“Walk-forward校准”页面
- 软件审查加入 walk-forward 校准检查项
- 安全研究流水线加入 walk-forward 校准与 V2.6 报告

## 输出

- `reports/walk_forward_calibration/walk_forward_calibration_report.html`
- `reports/v2_6_research_report/v2_6_research_report.html`

## 说明

V2.6 仍然不开放真实自动交易。该版本重点用于判断模型校准概率是否在滚动样本外窗口中稳定。
