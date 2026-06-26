# Data And Artifacts

The repository stores code and documentation. Runtime artifacts stay local.

## Tracked In Git

- `src/crypto_quant/**`: package source
- `scripts/**`: command-line entrypoints
- `frontend/app.py`: Streamlit dashboard
- `config/config.yaml`: default safe configuration
- `docs/**`: system documentation
- `tests/**`: smoke and contract tests
- `.env.example`: environment-variable template
- `.gitkeep`: placeholder files for important runtime directories

## Ignored By Git

- `.venv/`
- `.env` and `.env.*`
- private keys or certificates
- `data/raw/**`
- `data/processed/**`
- `data/database/**`
- `models/**`
- `reports/**`
- `logs/**`
- `__pycache__/`

## Important Local Artifacts

| Path | Purpose |
| --- | --- |
| `data/raw/OKX_BTC_USDT_SWAP_4h.parquet` | Historical OKX 4H candles |
| `data/processed/*_features.parquet` | Feature table |
| `data/processed/*_dataset.parquet` | Model training dataset |
| `data/database/realtime_market.sqlite` | Realtime OKX candle database |
| `data/database/paper_trading.sqlite` | Local paper trading state |
| `models/*.joblib` | Trained sklearn models |
| `reports/**` | Generated diagnostics, charts and HTML reports |
| `logs/**` | Runtime logs |

## Artifact Policy

- Do not commit raw market data by default.
- Do not commit trained models by default.
- Do not commit generated reports by default.
- Do not commit real credentials.
- Prefer reproducible scripts and docs over storing bulky outputs.

## When To Promote Artifacts

An artifact may be promoted outside the local workspace only when it has a clear operational purpose:

- release package
- model registry entry
- reproducibility bundle
- audit archive
- manually reviewed deployment bundle

Any promoted artifact should include config version, git commit, data range and validation summary.

