# BTC Quant Framework V3.0.7

V3.0.7 improves realtime market-data resilience and makes WebUI network failures easier to understand.

## Added

- OKX realtime WebSocket error classification for transient network failures.
- Explicit `ConnectionResetError(10054)` handling as a retryable connection reset.
- Realtime status metadata for:
  - current attempt
  - next reconnect attempt
  - maximum reconnect count
  - reconnect sleep seconds
  - structured error details
- Streamlit **实时行情** connection-health panel.
- UI controls for realtime sample reconnect count, reconnect wait time and environment-proxy bypass.
- OKX REST connectivity diagnostic button in the realtime page.

## Changed

- Successful realtime messages now clear stale `last_error` values.
- UI script execution now catches timeouts and process-launch exceptions instead of surfacing a Streamlit page crash.
- Project version updated to `3.0.7`.

## Safety

- The changes only affect public market-data and local UI workflows.
- No live-trading or order-submission controls are added.
- Realtime retries are bounded by the configured reconnect count.
