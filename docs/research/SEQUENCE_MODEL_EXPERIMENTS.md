# V2.8 序列模型实验层

V2.8 将 LSTM / GRU / TCN 做成独立研究实验层。它的目标不是替代表格模型主线，而是回答一个更实际的问题：**固定长度历史窗口是否真的能提高 BTC 低频方向预测的样本外表现？**

## 设计原则

- 默认只启用 `sequence_mlp`，不需要 PyTorch。
- `lstm`、`gru`、`tcn` 需要可选依赖 `torch`。
- 序列模型结果不会直接进入模拟盘执行或实盘执行。
- 只有当 walk-forward 表现、概率可靠性、成本压力和风控表现均优于表格模型时，才考虑后续进入候选池。

## 核心脚本

```bash
python scripts/check_sequence_model_backends.py
python scripts/run_sequence_model_experiments.py
python scripts/run_sequence_walk_forward.py
python scripts/build_v28_sequence_report.py
```

## 输出目录

```text
reports/sequence_models/
reports/sequence_walk_forward/
reports/v2_8_sequence_research_report/
```

重点查看：

```text
reports/sequence_models/sequence_model_summary.csv
reports/sequence_walk_forward/sequence_walk_forward_summary.csv
reports/v2_8_sequence_research_report/v2_8_sequence_research_report.html
```

## 可选安装 PyTorch

示例：

```bash
pip install -r requirements-sequence.txt
```

如果使用 RTX 4090，建议按 PyTorch 官网说明安装匹配 CUDA 的 wheel。安装后，将 `config/config.yaml` 中：

```yaml
sequence_models:
  include_torch_if_installed: true
sequence_walk_forward:
  include_torch_if_installed: true
```

并在 `models` 中保留 `lstm`、`gru`、`tcn`。

## 风险提示

序列模型更容易过拟合，尤其是在 BTC 低频 4h 数据中，样本数量并不算大。因此 V2.8 默认将序列模型作为实验层，而不是交易执行主线。
