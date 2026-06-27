from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any


def is_virtualenv_active() -> bool:
    """Return True when the current Python process is running inside a venv/virtualenv."""
    return bool(os.environ.get("VIRTUAL_ENV")) or sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def active_virtualenv_path() -> Path | None:
    """Best-effort path to the active virtual environment, if any."""
    env_path = os.environ.get("VIRTUAL_ENV")
    if env_path:
        return Path(env_path).resolve()
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return Path(sys.prefix).resolve()
    return None


def project_venv_path(root: Path) -> Path:
    return root / ".venv"


def project_venv_python(root: Path) -> Path | None:
    """Return the project .venv Python executable path when it exists."""
    root = root.resolve()
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def executable_is_under_project_venv(executable: str | Path, root: Path) -> bool:
    try:
        Path(executable).resolve().relative_to(project_venv_path(root).resolve())
        return True
    except Exception:
        return False


def running_in_project_venv(root: Path) -> bool:
    """Return True when the active interpreter is the repository-local .venv."""
    root = root.resolve()
    if executable_is_under_project_venv(sys.executable, root):
        return True
    active = active_virtualenv_path()
    if not active:
        return False
    try:
        return active.resolve() == project_venv_path(root).resolve()
    except Exception:
        return False


def resolve_python_executable(root: Path, prefer_project_venv: bool = True) -> Path:
    """Return the Python executable to use for local child processes.

    The managed-service console should normally launch services using the project
    .venv interpreter. This avoids starting long-running services with the wrong
    global Python environment when the WebUI was opened from a system shell.
    """
    root = root.resolve()
    if prefer_project_venv:
        venv_python = project_venv_python(root)
        if venv_python is not None:
            return venv_python
    return Path(sys.executable).resolve()


def activation_command(root: Path) -> str:
    """Return a user-facing activation command for the current platform."""
    if platform.system().lower().startswith("win"):
        return r".\.venv\Scripts\Activate.ps1"
    return "source .venv/bin/activate"


def cmd_activation_command() -> str:
    return r"call .venv\Scripts\activate.bat"


def runtime_summary(root: Path) -> dict[str, Any]:
    root = root.resolve()
    venv_python = project_venv_python(root)
    active = active_virtualenv_path()
    return {
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "virtualenv_active": is_virtualenv_active(),
        "active_virtualenv": str(active) if active else "",
        "project_venv": str(project_venv_path(root).resolve()),
        "project_venv_exists": project_venv_path(root).exists(),
        "project_venv_python": str(venv_python) if venv_python else "",
        "running_in_project_venv": running_in_project_venv(root),
        "recommended_powershell_activation": r".\.venv\Scripts\Activate.ps1",
        "recommended_cmd_activation": cmd_activation_command(),
        "recommended_bash_activation": "source .venv/bin/activate",
    }
