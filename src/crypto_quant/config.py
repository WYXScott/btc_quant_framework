from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import yaml


def project_root() -> Path:
    """Return repository root assuming this file is under src/crypto_quant."""
    return Path(__file__).resolve().parents[2]


def load_config(config_path: str | Path = "config/config.yaml") -> Dict[str, Any]:
    path = Path(config_path)
    if not path.is_absolute():
        path = project_root() / path
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


def resolve_path(relative_path: str | Path) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return project_root() / path
