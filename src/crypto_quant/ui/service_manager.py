from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crypto_quant.config import project_root, resolve_path


@dataclass(frozen=True)
class ManagedServiceSpec:
    name: str
    label: str
    script: str
    args: list[str]
    description: str
    category: str
    script_path: Path
    state_path: Path
    log_path: Path

    @property
    def command(self) -> list[str]:
        return [sys.executable, str(self.script_path), *self.args]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_rel(path: Path) -> str:
    root = project_root()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _pid_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return False
        return f'"{pid}"' in (proc.stdout or "")
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def configured_services(cfg: dict[str, Any]) -> dict[str, ManagedServiceSpec]:
    svc_cfg = cfg.get("managed_services", {}) or {}
    state_dir = resolve_path(svc_cfg.get("state_dir", "reports/services"))
    log_dir = resolve_path(svc_cfg.get("log_dir", "logs/services"))
    allowed = svc_cfg.get("allowed", {}) or {}
    specs: dict[str, ManagedServiceSpec] = {}
    scripts_dir = project_root() / "scripts"
    for name, raw in allowed.items():
        item = raw if isinstance(raw, dict) else {}
        script = str(item.get("script", "")).strip()
        if not name or not script:
            continue
        script_path = scripts_dir / script
        try:
            script_path.resolve().relative_to(scripts_dir.resolve())
        except ValueError:
            continue
        specs[str(name)] = ManagedServiceSpec(
            name=str(name),
            label=str(item.get("label") or name),
            script=script,
            args=[str(x) for x in item.get("args", []) or []],
            description=str(item.get("description") or ""),
            category=str(item.get("category") or "general"),
            script_path=script_path,
            state_path=state_dir / f"{name}.json",
            log_path=log_dir / f"{name}.log",
        )
    return specs


def get_service_status(cfg: dict[str, Any], name: str) -> dict[str, Any]:
    specs = configured_services(cfg)
    if name not in specs:
        return {"name": name, "status": "unknown", "running": False, "message": "service is not configured"}
    spec = specs[name]
    state = _read_json(spec.state_path)
    pid = state.get("pid")
    try:
        pid_int = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        pid_int = None
    running = _pid_running(pid_int)
    status = "running" if running else str(state.get("status") or "stopped")
    if not running and status == "running":
        status = "exited_or_stale"
        state["status"] = status
        state["running"] = False
        state["updated_at_utc"] = _now()
        state.setdefault("message", "process is no longer running")
        _write_json(spec.state_path, state)

    return {
        "name": spec.name,
        "label": spec.label,
        "category": spec.category,
        "script": spec.script,
        "args": " ".join(spec.args),
        "pid": pid_int,
        "status": status,
        "running": running,
        "started_at_utc": state.get("started_at_utc", ""),
        "stopped_at_utc": state.get("stopped_at_utc", ""),
        "updated_at_utc": state.get("updated_at_utc", ""),
        "message": state.get("message", ""),
        "description": spec.description,
        "state_path": _safe_rel(spec.state_path),
        "log_path": _safe_rel(spec.log_path),
        "command": " ".join(spec.command),
        "script_exists": spec.script_path.exists(),
    }


def service_status_rows(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    return [get_service_status(cfg, name) for name in configured_services(cfg)]


def start_service(cfg: dict[str, Any], name: str) -> dict[str, Any]:
    specs = configured_services(cfg)
    if name not in specs:
        return {"name": name, "status": "blocked", "running": False, "message": "service is not configured"}
    spec = specs[name]
    if not spec.script_path.exists():
        return {"name": name, "status": "blocked", "running": False, "message": f"script not found: {spec.script}"}

    current = get_service_status(cfg, name)
    if current.get("running"):
        current["message"] = "service is already running"
        return current

    spec.state_path.parent.mkdir(parents=True, exist_ok=True)
    spec.log_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"\n\n=== start {name} at {_now()} ===\ncommand: {' '.join(spec.command)}\n"
    with spec.log_path.open("a", encoding="utf-8") as f:
        f.write(header)

    creationflags = 0
    if os.name == "nt":
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        log_handle = spec.log_path.open("ab")
        try:
            proc = subprocess.Popen(
                spec.command,
                cwd=project_root(),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        finally:
            log_handle.close()
    except Exception as exc:
        state = {
            "name": spec.name,
            "label": spec.label,
            "script": spec.script,
            "args": spec.args,
            "status": "start_failed",
            "running": False,
            "message": repr(exc),
            "updated_at_utc": _now(),
            "log_path": _safe_rel(spec.log_path),
        }
        _write_json(spec.state_path, state)
        return get_service_status(cfg, name)

    state = {
        "name": spec.name,
        "label": spec.label,
        "script": spec.script,
        "args": spec.args,
        "pid": int(proc.pid),
        "status": "running",
        "running": True,
        "started_at_utc": _now(),
        "updated_at_utc": _now(),
        "message": "started",
        "command": spec.command,
        "state_path": _safe_rel(spec.state_path),
        "log_path": _safe_rel(spec.log_path),
    }
    _write_json(spec.state_path, state)
    return get_service_status(cfg, name)


def stop_service(cfg: dict[str, Any], name: str) -> dict[str, Any]:
    specs = configured_services(cfg)
    if name not in specs:
        return {"name": name, "status": "blocked", "running": False, "message": "service is not configured"}
    spec = specs[name]
    current = get_service_status(cfg, name)
    pid = current.get("pid")
    if not current.get("running") or not pid:
        state = _read_json(spec.state_path)
        state.update(
            {
                "status": "stopped",
                "running": False,
                "stopped_at_utc": _now(),
                "updated_at_utc": _now(),
                "message": "service was not running",
            }
        )
        _write_json(spec.state_path, state)
        return get_service_status(cfg, name)

    message = "stopped"
    status = "stopped"
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc.returncode != 0:
                status = "stop_failed"
                message = (proc.stderr or proc.stdout or "").strip() or f"taskkill returned {proc.returncode}"
        else:
            os.kill(int(pid), 15)
    except Exception as exc:
        status = "stop_failed"
        message = repr(exc)

    state = _read_json(spec.state_path)
    state.update(
        {
            "status": status,
            "running": False,
            "stopped_at_utc": _now(),
            "updated_at_utc": _now(),
            "message": message,
        }
    )
    _write_json(spec.state_path, state)
    try:
        spec.log_path.open("a", encoding="utf-8").write(f"\n=== stop {name} at {_now()} status={status} ===\n")
    except Exception:
        pass
    return get_service_status(cfg, name)


def restart_service(cfg: dict[str, Any], name: str) -> dict[str, Any]:
    stop_service(cfg, name)
    return start_service(cfg, name)


def tail_service_log(cfg: dict[str, Any], name: str, max_chars: int = 12000) -> str:
    specs = configured_services(cfg)
    if name not in specs:
        return ""
    path = specs[name].log_path
    if not path.exists():
        return ""
    max_bytes = max(4096, int(max_chars) * 2)
    with path.open("rb") as f:
        size = path.stat().st_size
        f.seek(max(0, size - max_bytes))
        raw = f.read()
    return raw.decode("utf-8", errors="replace")[-max_chars:]


def service_spec_rows(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            **asdict(spec),
            "script_path": _safe_rel(spec.script_path),
            "state_path": _safe_rel(spec.state_path),
            "log_path": _safe_rel(spec.log_path),
            "command": " ".join(spec.command),
        }
        for spec in configured_services(cfg).values()
    ]
