# V2.6 Walk-forward 概率校准

V2.6 将 V2.5 的固定切分概率校准升级为严格的滚动校准流程：

```text
train window       -> 训练基础分类器
calibration window -> 只用训练后、测试前的数据拟合概率校准器
test window        -> 输出样本外 raw / calibrated probability
```

这个设计的目的，是避免后验校准器在测试窗口上产生时间泄露。对于 BTC 低频杠杆交易，模型概率不仅影响是否入场，也会影响目标敞口，因此校准流程必须比普通分类任务更严格。

## 主要脚本

```bash
python scripts/run_walk_forward_calibration.py
python scripts/build_v26_research_report.py
```

## 主要输出

```text
reports/walk_forward_calibration/walk_forward_calibration_summary.json
reports/walk_forward_calibration/walk_forward_calibrated_predictions.csv
reports/walk_forward_calibration/walk_forward_calibrated_folds.csv
reports/walk_forward_calibration/walk_forward_reliability_raw.csv
reports/walk_forward_calibration/walk_forward_reliability_calibrated.csv
reports/walk_forward_calibration/walk_forward_confidence_tiers.csv
reports/walk_forward_calibration/walk_forward_calibrated_summary.csv
reports/walk_forward_calibration/walk_forward_calibration_report.html
reports/v2_6_research_report/v2_6_research_report.html
```

## 重点看什么

1. `test_calibrated_brier` 是否低于 `test_raw_brier`。
2. `test_calibrated_ece` 是否低于 `test_raw_ece`。
3. 每个 fold 的改善是否稳定，而不是只在个别区间改善。
4. `walk_forward_confidence_tiers.csv` 中强信号层的真实正样本率和未来收益是否高于弱信号层。
5. 动态敞口回测是否在手续费、滑点、资金费率和强平风险报告之后仍有优势。

## 与 V2.5 的区别

V2.5 使用固定 train / valid / test 切分：

```text
train -> 训练模型
valid -> 拟合校准器
test  -> 评估
```

V2.6 在每个时间窗口重复执行上述逻辑：

```text
fold 1: train1 -> calibrate1 -> test1
fold 2: train2 -> calibrate2 -> test2
...
```

因此 V2.6 的结果更接近真实运行环境。进入长期模拟盘前，优先参考 V2.6 报告，而不是只看 V2.5 固定切分报告。

## 安全边界

V2.6 仍然只用于研究、回测和模拟盘，不开放实盘自动交易。
