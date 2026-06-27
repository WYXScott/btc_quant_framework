from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crypto_quant.config import project_root, resolve_path
from crypto_quant.utils.runtime_env import resolve_python_executable, runtime_summary


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
    python_executable: Path

    @property
    def command(self) -> list[str]:
        return [str(self.python_executable), str(self.script_path), *self.args]


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


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


def _process_command_line(pid: int | None) -> str:
    if not pid or pid <= 0:
        return ""
    if os.name == "nt":
        commands = [
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\").CommandLine",
            ],
            ["wmic", "process", "where", f"ProcessId={int(pid)}", "get", "CommandLine", "/value"],
        ]
        for command in commands:
            try:
                proc = subprocess.run(command, capture_output=True, text=True, timeout=5)
            except Exception:
                continue
            output = (proc.stdout or "").strip()
            if not output:
                continue
            if "CommandLine=" in output:
                output = output.split("CommandLine=", 1)[-1].strip()
            return output
        return ""
    try:
        proc = subprocess.run(["ps", "-p", str(int(pid)), "-o", "args="], capture_output=True, text=True, timeout=5)
    except Exception:
        return ""
    return (proc.stdout or "").strip()


def _norm_cmd_text(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip().lower()


def _state_command_text(state: dict[str, Any]) -> str:
    command = state.get("command") or state.get("command_line") or ""
    if isinstance(command, list):
        return " ".join(str(x) for x in command)
    return str(command or "")


def _pid_matches_service(pid: int | None, spec: ManagedServiceSpec, state: dict[str, Any]) -> tuple[bool, str, str]:
    """Verify that a recorded PID still belongs to this managed service.

    PID reuse is a real risk for long-running local service consoles. We therefore
    treat a PID as controllable only when the OS command line still points at the
    configured service script. If the command line cannot be inspected, stop/restart
    refuses to kill the PID instead of guessing.
    """
    if not _pid_running(pid):
        return False, "process_not_running", ""
    if pid == os.getpid():
        return False, "refusing_to_match_current_process", ""
    command_line = _process_command_line(pid)
    norm_running = _norm_cmd_text(command_line)
    if not norm_running:
        return False, "unable_to_verify_process_command_line", command_line

    expected_tokens = {
        _norm_cmd_text(spec.script),
        _norm_cmd_text(spec.script_path),
        _norm_cmd_text(spec.script_path.resolve()),
    }
    stored_text = _norm_cmd_text(_state_command_text(state))
    if stored_text:
        expected_tokens.add(stored_text)
    expected_tokens = {token for token in expected_tokens if token}

    if any(token in norm_running for token in expected_tokens):
        return True, "matched", command_line
    return False, "pid_command_mismatch", command_line


def configured_services(cfg: dict[str, Any]) -> dict[str, ManagedServiceSpec]:
    svc_cfg = cfg.get("managed_services", {}) or {}
    if svc_cfg.get("enabled") is False:
        return {}
    state_dir = resolve_path(svc_cfg.get("state_dir", "reports/services"))
    log_dir = resolve_path(svc_cfg.get("log_dir", "logs/services"))
    allowed = svc_cfg.get("allowed", {}) or {}
    runtime_cfg = cfg.get("runtime", {}) or {}
    python_executable = resolve_python_executable(
        project_root(),
        prefer_project_venv=bool(runtime_cfg.get("prefer_project_venv", True)),
    )
    specs: dict[str, ManagedServiceSpec] = {}
    scripts_dir = project_root() / "scripts"
    scripts_root = scripts_dir.resolve()
    for name, raw in allowed.items():
        item = raw if isinstance(raw, dict) else {}
        script = str(item.get("script", "")).strip()
        if not name or not script:
            continue
        raw_script_path = Path(script)
        if raw_script_path.is_absolute():
            continue
        script_path = (scripts_dir / raw_script_path).resolve()
        try:
            script_path.relative_to(scripts_root)
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
            python_executable=python_executable,
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

    pid_is_running = _pid_running(pid_int)
    matched, match_reason, command_line = _pid_matches_service(pid_int, spec, state) if pid_is_running else (False, "process_not_running", "")
    running = bool(matched)
    previous_status = str(state.get("status") or "stopped")
    status = "running" if running else previous_status
    message = str(state.get("message") or "")

    if pid_is_running and not matched:
        status = "stale_pid_mismatch"
        message = f"Recorded PID is running but was not verified as this service: {match_reason}"
        state.update(
            {
                "status": status,
                "running": False,
                "pid_running": True,
                "pid_match_reason": match_reason,
                "observed_command_line": command_line,
                "updated_at_utc": _now(),
                "message": message,
            }
        )
        _write_json(spec.state_path, state)
    elif not pid_is_running and previous_status == "running":
        status = "exited_or_stale"
        message = message or "process is no longer running"
        state.update(
            {
                "status": status,
                "running": False,
                "pid_running": False,
                "pid_match_reason": match_reason,
                "updated_at_utc": _now(),
                "message": message,
            }
        )
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
        "pid_running": pid_is_running,
        "pid_match_reason": match_reason,
        "started_at_utc": state.get("started_at_utc", ""),
        "stopped_at_utc": state.get("stopped_at_utc", ""),
        "updated_at_utc": state.get("updated_at_utc", ""),
        "message": message,
        "description": spec.description,
        "state_path": _safe_rel(spec.state_path),
        "log_path": _safe_rel(spec.log_path),
        "command": " ".join(spec.command),
        "python_executable": str(spec.python_executable),
        "observed_command_line": command_line,
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
    if current.get("pid_running") and current.get("status") == "stale_pid_mismatch":
        return {
            **current,
            "status": "blocked",
            "running": False,
            "message": "Recorded PID is running but does not match this service. Inspect the state file before starting another copy.",
        }

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

    time.sleep(0.05)
    command_line = _process_command_line(int(proc.pid))
    runtime = runtime_summary(project_root())
    state = {
        "name": spec.name,
        "label": spec.label,
        "script": spec.script,
        "script_path": _safe_rel(spec.script_path),
        "args": spec.args,
        "pid": int(proc.pid),
        "status": "running",
        "running": True,
        "started_at_utc": _now(),
        "updated_at_utc": _now(),
        "message": "started",
        "command": spec.command,
        "command_line": command_line,
        "python_executable": str(spec.python_executable),
        "launcher_python_executable": sys.executable,
        "runtime": runtime,
        "cwd": str(project_root()),
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
    if current.get("pid_running") and not current.get("running"):
        state = _read_json(spec.state_path)
        state.update(
            {
                "status": "stale_pid_mismatch",
                "running": False,
                "updated_at_utc": _now(),
                "message": "Refused to stop because the recorded PID was not verified as this managed service.",
            }
        )
        _write_json(spec.state_path, state)
        return get_service_status(cfg, name)
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
            os.kill(int(pid), signal.SIGTERM)
            for _ in range(20):
                if not _pid_running(int(pid)):
                    break
                time.sleep(0.25)
            if _pid_running(int(pid)):
                os.kill(int(pid), signal.SIGKILL)
                message = "stopped with SIGKILL after SIGTERM timeout"
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
    stopped = stop_service(cfg, name)
    if stopped.get("status") in {"stop_failed", "stale_pid_mismatch", "blocked"} and stopped.get("pid_running"):
        return stopped
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
