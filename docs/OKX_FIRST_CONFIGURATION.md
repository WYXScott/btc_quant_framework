# OKX-First Configuration Notes

V3.2.1 narrows the supported main workflow to:

```text
OKX public REST/WebSocket market data
→ local parquet/SQLite storage
→ model research and walk-forward validation
→ local SQLite paper trading
→ operations reports and Streamlit monitoring
```

The default configuration intentionally does **not** enable private exchange order submission.

## Supported main path

| Layer | Supported default |
|---|---|
| Historical data | OKX native REST candles |
| Realtime data | OKX public WebSocket candles |
| Research storage | local parquet files |
| Runtime state | local SQLite databases |
| Trading simulation | local paper account only |
| Dashboard services | OKX realtime listener and local paper loop |
| Live trading | blocked by safety gates |

## Fields intentionally kept as future placeholders

Some sections remain in `config/config.yaml` because old research scripts may still read their keys, but they are disabled or treated as future adapter placeholders:

- `native_protection.enabled: false`
- `user_stream.enabled: false`
- `ensemble_demo_execution.enabled: false`
- `ensemble_demo_sync.enabled: false`

These are not part of the current recommended workflow. A future OKX private adapter should be implemented behind an explicit adapter interface before these sections are re-enabled.

## Removed from the main operator path

V3.2.1 removes Binance-oriented wording from the default `.env.example`, main configuration comments, stability execution checks, and dashboard-facing workflow descriptions. Legacy Binance research/demo files may still exist in the repository as archival scaffolding, but they are not exposed as the recommended path.

## Recommended local commands

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\check_runtime_env.py --strict
python scripts\run_stability_check.py
python scripts\manage_services.py status
python tests\smoke_test.py
.\start_dashboard.cmd
```

CMD:

```bat
call .venv\Scripts\activate.bat
python scripts\check_runtime_env.py --strict
python scripts\run_stability_check.py
python scripts\manage_services.py status
python tests\smoke_test.py
start_dashboard.cmd
```

## Funding-rate realism

Funding-rate data is optional. In V3.2.1 the default funding file is:

```text
data/raw/OKX_BTC_USDT_SWAP_funding_rates.parquet
```

If funding download fails, market-realism reports can still run with zero or missing funding assumptions. Treat funding download failures as a realism-data limitation rather than a training blocker.
