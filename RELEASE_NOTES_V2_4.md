# Release Notes V2.4

## 版本定位

V2.4 是“数据质量检查 + 回测真实性增强 + 更严格时间序列验证”版本，仍然不开放实盘自动交易。

## 新增内容

- 新增 `crypto_quant.data.quality`
  - 缺失K线检查
  - 重复时间戳检查
  - OHLC一致性检查
  - NaN / Inf / 非正价格检查
  - 极端跳价与极端K线区间检查
  - 零成交量比例检查

- 新增 `crypto_quant.realism.market`
  - 资金费率对权益曲线的影响估算
  - 强平价格近似估算
  - 强平缓冲区监控
  - 回测真实性 HTML 报告

- 新增 `crypto_quant.realism.funding`
  - Binance USD-M funding rate 下载工具
  - 资金费率历史数据 Parquet 存储

- 新增 `crypto_quant.realism.validation`
  - Purged / Embargo 时间序列交叉验证
  - 降低标签泄露和近邻泄露风险

- 前端新增页面：`数据质量与真实性`

## 新增脚本

```text
scripts/run_data_quality_check.py
scripts/download_funding_rates.py
scripts/run_market_realism_report.py
scripts/run_purged_embargo_cv.py
```

## 安全边界

- 不开放实盘自动交易；
- 不新增真实下单按钮；
- Demo/Testnet 仍保持确认短语和 dry-run 约束；
- Live trading master switch 默认关闭。
