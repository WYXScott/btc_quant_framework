# Service Operations

V3.1.0 adds a local managed-service layer for tasks that are useful as long-running background processes.

The service layer is intentionally conservative:

- services must be listed in `config/config.yaml` under `managed_services.allowed`
- each service maps to a script under `scripts/`
- status is written to `reports/services`
- logs are written to `logs/services`
- real-money trading remains blocked by the existing safety switches
- stop/restart verifies the recorded PID against the expected service command line before killing a process

## Managed Services

The initial services are:

| Service | Script | Purpose |
| --- | --- | --- |
| `okx_realtime_listener` | `scripts/run_okx_realtime_listener.py` | Persist OKX public `candle1m` and `candle4H` WebSocket data to SQLite. |
| `paper_ensemble_loop` | `scripts/paper_ensemble_loop.py` | Run the local ensemble paper-trading loop against SQLite state. |

Both are local/public-data workflows. They do not submit live orders.

## WebUI Usage

Start the dashboard:

```powershell
python scripts/run_dashboard.py
```

Open:

```text
http://localhost:8501
```

Use **服务控制台** to:

- view configured services
- start a service
- stop a service
- restart a service
- refresh process status
- inspect the latest log tail

## CLI Usage

List configured services:

```powershell
python scripts/manage_services.py list
```

Show current status:

```powershell
python scripts/manage_services.py status
python scripts/manage_services.py status okx_realtime_listener
```

Start and stop:

```powershell
python scripts/manage_services.py start okx_realtime_listener
python scripts/manage_services.py stop okx_realtime_listener
```

Read logs:

```powershell
python scripts/manage_services.py logs okx_realtime_listener
```

## Files

Service state files:

```text
reports/services/<service_name>.json
```

Service logs:

```text
logs/services/<service_name>.log
```

These are runtime artifacts and are intentionally not committed.

## Safety Notes

Do not add exchange-private or order-submitting scripts to `managed_services.allowed` until the system has a separate approval workflow, permission audit and execution gate for services.

For now, keep managed services limited to:

- public market-data listeners
- local paper-trading loops
- local monitoring/reporting processes

Use `python scripts/run_stability_check.py` after adding a service. It checks that configured service scripts exist, remain scoped under `scripts/`, and that the service state/log directories are configured.

If a service status shows `stale_pid_mismatch`, do not force-stop it from the console. It means the recorded PID is alive but does not match the configured service command line; inspect `reports/services/<service>.json` and the OS process list first.
