from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
from urllib import request, error


@dataclass(frozen=True)
class AlertMessage:
    """A small, transport-neutral alert record.

    The project intentionally keeps alert delivery optional. Console and JSONL
    alerts are always safe. Webhook delivery is disabled unless configured.
    """

    level: str
    title: str
    message: str
    payload: dict[str, Any] | None = None
    timestamp_utc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data["timestamp_utc"] is None:
            data["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        return data


class AlertRouter:
    """Route alerts to console, JSONL file, and optional generic webhook.

    Environment variables are used for any secret-bearing destination. The
    default configuration never sends data outside the local machine.
    """

    def __init__(self, cfg: dict[str, Any], *, project_root: Path | None = None):
        self.cfg = cfg
        self.alert_cfg = cfg.get("alerts", {}) or {}
        self.project_root = project_root or Path.cwd()

    @classmethod
    def from_config(cls, cfg: dict[str, Any], *, project_root: Path | None = None) -> "AlertRouter":
        return cls(cfg, project_root=project_root)

    def _jsonl_path(self) -> Path | None:
        path = self.alert_cfg.get("jsonl_path")
        if not path:
            return None
        p = Path(path)
        if not p.is_absolute():
            p = self.project_root / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _write_jsonl(self, data: dict[str, Any]) -> dict[str, Any]:
        path = self._jsonl_path()
        if path is None:
            return {"enabled": False}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
        return {"enabled": True, "path": str(path)}

    def _send_webhook(self, data: dict[str, Any]) -> dict[str, Any]:
        webhook_cfg = self.alert_cfg.get("webhook", {}) or {}
        if not webhook_cfg.get("enabled", False):
            return {"enabled": False}
        env_name = webhook_cfg.get("url_env", "BTCQ_ALERT_WEBHOOK_URL")
        url = os.getenv(str(env_name), "").strip()
        if not url:
            return {"enabled": True, "status": "skipped", "reason": f"Environment variable {env_name} is not set."}
        timeout = float(webhook_cfg.get("timeout_seconds", 5.0))
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        req = request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - user configured endpoint
                return {"enabled": True, "status": "sent", "http_status": resp.status}
        except (error.URLError, TimeoutError, OSError) as exc:
            return {"enabled": True, "status": "failed", "error": str(exc)}

    def notify(self, alert: AlertMessage) -> dict[str, Any]:
        data = alert.to_dict()
        results: dict[str, Any] = {}
        if self.alert_cfg.get("console", True):
            print(json.dumps({"alert": data}, ensure_ascii=False, default=str))
            results["console"] = {"enabled": True}
        else:
            results["console"] = {"enabled": False}
        results["jsonl"] = self._write_jsonl(data)
        results["webhook"] = self._send_webhook(data)
        return {"alert": data, "delivery": results}
