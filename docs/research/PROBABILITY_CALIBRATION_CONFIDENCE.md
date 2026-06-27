# V2.5 概率校准与信号可信度分层

## 背景

树模型、boosting 模型和很多非线性分类器的 `predict_proba` 往往不等于真实胜率。直接把未校准概率用于杠杆仓位控制，会导致两个问题：

1. 概率看起来很高，但实际命中率并没有对应提高。
2. 仓位随概率放大，可能把模型过度自信直接转化为杠杆风险。

V2.5 新增后验概率校准和信号可信度分层，用于把模型输出转化为更稳定的交易研究信号。

## 新增脚本

```bash
python scripts/train_calibrated_model.py
python scripts/run_signal_confidence_report.py
python scripts/run_calibrated_ml_backtest.py
```

## 输出文件

```text
reports/calibration/calibration_metrics.json
reports/calibration/raw_vs_calibrated_metrics.csv
reports/calibration/reliability_raw.csv
reports/calibration/reliability_calibrated.csv
reports/calibration/calibration_report.html
reports/signal_confidence/confidence_tier_table.csv
reports/signal_confidence/signal_confidence_report.html
reports/calibrated_ml_backtest/calibrated_ml_summary.csv
```

## 信号层级

默认配置：

| 层级 | 校准概率 | 目标敞口 |
|---|---:|---:|
| no_trade | < 0.55 | 0x |
| weak_long | >= 0.55 | 0.75x |
| medium_long | >= 0.60 | 1.5x |
| strong_long | >= 0.65 | 2.5x |

如果启用趋势过滤，且 BTC 未满足 `close > MA120` 与 `MA24 > MA120`，即使概率较高也会被降为 `blocked_by_trend`。

## 重点查看指标

- `Brier score`：越低越好，衡量概率误差。
- `ECE`：Expected Calibration Error，越低越好。
- `MCE`：Maximum Calibration Error，最大分桶校准误差。
- `reliability_calibrated.csv`：每个概率桶的预测概率与实际上涨率。
- `confidence_tier_table.csv`：每个信号层级的真实收益表现。

## 使用建议

不要只看校准后的 ROC-AUC。校准的目的不是提高排序能力，而是让“概率值本身”更接近真实频率。对于杠杆交易，更应该关注：

- 校准后 Brier/ECE 是否下降；
- strong_long 的未来收益是否显著优于 weak_long；
- strong_long 的样本量是否足够；
- 加入成本和滑点后，动态敞口策略是否仍然稳定；
- 在 Purged/Embargo CV 下是否仍然有类似结论。

当前版本仍然只用于研究、回测和模拟盘，不开放实盘自动交易。
