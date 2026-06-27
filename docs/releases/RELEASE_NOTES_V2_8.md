# Release Notes V2.8

## 新增

- V2.8 序列模型实验层。
- 固定长度窗口序列数据构造。
- 内置 `sequence_mlp` flattened-window baseline。
- 可选 PyTorch `lstm` / `gru` / `tcn` 实验模型。
- 序列模型固定切分实验报告。
- 序列模型 walk-forward 实验报告。
- Streamlit 前端新增“序列模型实验”页面。
- 新增 `requirements-sequence.txt`。

## 边界

- 不开放实盘自动交易。
- 序列模型不直接接模拟盘或 Demo/Testnet 执行。
- PyTorch 不是默认依赖，未安装时自动跳过 LSTM/GRU/TCN。
