from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from crypto_quant.config import project_root


def setup_runtime_logging(cfg: dict[str, Any], *, component: str = "demo_service") -> Path:
    """Configure console + rotating file logging for long-running scripts."""

    root = project_root()
    log_cfg = cfg.get("logging", {}) or {}
    log_dir = Path(log_cfg.get("log_dir", "logs"))
    if not log_dir.is_absolute():
        log_dir = root / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{component}.log"
    max_bytes = int(log_cfg.get("max_bytes", 5_000_000))
    backup_count = int(log_cfg.get("backup_count", 5))
    level_name = str(log_cfg.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Avoid duplicate handlers when scripts are called repeatedly.
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.setLevel(level)
    file_handler = RotatingFileHandler(log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(stream)
    root_logger.addHandler(file_handler)
    return log_path
