# V2.4 数据质量与回测真实性说明

## 1. 为什么需要数据质量检查

低频 BTC 策略看起来稳健，很多时候不是模型有效，而是数据存在隐性问题，例如缺失K线、重复时间戳、异常跳价、OHLC错误或成交量异常。V2.4 在训练模型前加入 `run_data_quality_check.py`，用于先判断原始K线是否可靠。

运行：

```bash
python scripts/run_data_quality_check.py
```

输出：

```text
reports/data_quality/data_quality_report.json
reports/data_quality/data_quality_issues.csv
reports/data_quality/data_quality_report.html
```

重点看：

- `status` 是否为 `pass`；
- `critical_count` 是否为 0；
- 是否存在 `missing_candles`、`duplicate_timestamp`、`ohlc_consistency` 等问题。

## 2. 资金费率

如果使用 BTC U本位合约，资金费率会影响低频持仓收益。V2.4 支持可选下载资金费率：

```bash
python scripts/download_funding_rates.py
```

输出：

```text
data/raw/BTCUSDT_funding_rates.parquet
reports/market_realism/funding_download_report.json
```

如果资金费率下载失败，其他研究流程仍可运行，市场真实性报告会按 0 funding 处理。

## 3. 回测真实性报告

运行：

```bash
python scripts/run_market_realism_report.py
```

输出：

```text
reports/market_realism/market_realism_report.json
reports/market_realism/market_realism_enriched_result.csv
reports/market_realism/market_realism_report.html
```

重点看：

- `funding_adjusted_final_equity`；
- `total_funding_return_cost`；
- `min_liquidation_buffer_observed`；
- `liquidation_buffer_warning_bars`；
- `estimated_liquidation_breach_bars`。

注意：强平价格是近似估算，不是交易所精确公式。正式实盘前必须按具体交易所、保证金模式、仓位模式重新核验。

## 4. Purged / Embargo CV

普通时间切分仍可能存在标签泄露或近邻泄露。V2.4 加入更严格的 Purged/Embargo 交叉验证：

```bash
python scripts/run_purged_embargo_cv.py
```

输出：

```text
reports/validation/purged_embargo_cv_metrics.csv
reports/validation/purged_embargo_cv_predictions.csv
reports/validation/purged_embargo_cv_report.html
```

如果该指标明显低于普通模型诊断结果，应优先怀疑过拟合或标签泄露，而不是提高杠杆。
