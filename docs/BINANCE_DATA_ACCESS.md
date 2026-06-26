# Binance 数据访问说明（V3.0.1）

本项目默认继续使用 Binance 公共行情数据，不需要 API Key。

## 推荐下载器

V3.0.1 默认使用：

```yaml
exchange:
  name: binance
  market_type: future

symbol:
  ccxt_symbol: BTC/USDT:USDT
  raw_symbol: BTCUSDT

download:
  downloader: binance_native
  base_url: https://fapi.binance.com
  timeout_seconds: 30
  max_retries: 5
  use_env_proxy: true
```

这个下载器直接访问 Binance USD-M Futures K线接口 `/fapi/v1/klines`，不再先调用 CCXT `load_markets()`，因此可以避开 `exchangeInfo` 超时导致的中断。

## 如果你的网络需要代理

在 PowerShell 当前窗口中设置：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"
```

然后先测试：

```bash
python scripts/check_binance_connectivity.py
```

确认 `fapi/v1/time` 和 `fapi/v1/klines` 可以访问后，再运行：

```bash
python scripts/download_ohlcv.py
```

## 如果仍然超时

1. 确认代理端口是否正确；
2. 确认代理规则是否允许 `fapi.binance.com`；
3. 在浏览器或命令行测试 `https://fapi.binance.com/fapi/v1/time`；
4. 必要时将 `download.timeout_seconds` 提高到 60。

