# Release Notes V2.5

## 概率校准与交易信号可信度分层

V2.5 不开放实盘交易，重点增强模型输出概率的可解释性和交易可用性。

新增内容：

- Post-hoc probability calibration：`isotonic` / `sigmoid` / `none`。
- 保存校准模型：`models/btc_direction_model_calibrated.joblib`。
- Raw vs calibrated 对比：Brier score、ECE、MCE、log loss、ROC-AUC。
- 可靠性曲线与概率分桶收益表。
- 信号可信度分层：`no_trade`、`weak_long`、`medium_long`、`strong_long`。
- 可信度到动态目标敞口映射：例如 0x / 0.75x / 1.5x / 2.5x。
- 校准概率驱动的动态仓位回测。
- Streamlit 前端新增“概率校准与信号可信度”页面。

推荐流程：

```bash
python scripts/download_ohlcv.py
python scripts/run_data_quality_check.py
python scripts/build_features.py
python scripts/train_model.py
python scripts/train_calibrated_model.py
python scripts/run_signal_confidence_report.py
python scripts/run_calibrated_ml_backtest.py
python scripts/run_purged_embargo_cv.py
python scripts/audit_package.py
```

注意：校准模型仍然只用于研究、回测和模拟盘，不代表可以进入实盘。
