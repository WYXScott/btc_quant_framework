from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib
import os
from pathlib import Path
import platform
import sys
from typing import Any

from crypto_quant.config import project_root
from crypto_quant.paper.database import PaperStore


@dataclass(frozen=True)
class CheckResult:
    """Single deployment-health check result.

    status convention:
        pass  = ready / safe
        warn  = usable, but action is recommended before long running demo
        fail  = must be fixed before running the service
        info  = diagnostic information only
    """

    name: str
    status: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeploymentHealthReport:
    timestamp_utc: str
    overall_status: str
    project_root: str
    checks: list[CheckResult]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = [c.to_dict() for c in self.checks]
        return data

    @property
    def has_failures(self) -> bool:
        return any(c.status == "fail" for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(c.status == "warn" for c in self.checks)


class DeploymentHealthChecker:
    """Conservative pre-flight checks for paper/Demo deployment.

    The checker intentionally treats live trading settings as failures. V1.0 is
    a deployment-ready Demo system, not a live-money system.
    """

    REQUIRED_IMPORTS = ["pandas", "numpy", "yaml"]
    OPTIONAL_IMPORTS = ["ccxt", "sklearn", "joblib", "matplotlib", "websocket"]

    def __init__(self, cfg: dict[str, Any], *, root: Path | None = None):
        self.cfg = cfg
        self.root = root or project_root()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _path(self, value: str | Path) -> Path:
        p = Path(value)
        return p if p.is_absolute() else self.root / p

    def check_python(self) -> CheckResult:
        version = sys.version_info
        ok = version >= (3, 10)
        return CheckResult(
            name="python_version",
            status="pass" if ok else "fail",
            message=f"Python {version.major}.{version.minor}.{version.micro} on {platform.system()} {platform.release()}",
            details={"executable": sys.executable, "required": ">=3.10"},
        )

    def check_imports(self) -> CheckResult:
        missing_required: list[str] = []
        missing_optional: list[str] = []
        versions: dict[str, str | None] = {}
        for mod_name in self.REQUIRED_IMPORTS + self.OPTIONAL_IMPORTS:
            try:
                mod = importlib.import_module(mod_name)
                versions[mod_name] = getattr(mod, "__version__", None)
            except Exception as exc:  # pragma: no cover - exact import failures vary by env
                target = missing_required if mod_name in self.REQUIRED_IMPORTS else missing_optional
                target.append(f"{mod_name}: {exc}")
        if missing_required:
            return CheckResult("required_imports", "fail", "Critical Python packages are not importable.", {"missing_required": missing_required, "missing_optional": missing_optional, "versions": versions})
        if missing_optional:
            return CheckResult("required_imports", "warn", "Some optional runtime packages are not importable. Install requirements.txt before data download, training, or Demo exchange access.", {"missing_optional": missing_optional, "versions": versions})
        return CheckResult("required_imports", "pass", "All required and optional Python packages are importable.", {"versions": versions})

    def check_directories(self) -> CheckResult:
        required_dirs = ["data/raw", "data/processed", "data/database", "models", "reports", "logs"]
        created = []
        for rel in required_dirs:
            p = self.root / rel
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
                created.append(rel)
        return CheckResult(
            "directories",
            "pass",
            "Required runtime directories exist.",
            {"required_dirs": required_dirs, "created": created},
        )

    def check_safety_config(self) -> CheckResult:
        broker = self.cfg.get("broker", {}) or {}
        safety = broker.get("safety", {}) or {}
        execution = self.cfg.get("execution", {}) or {}
        auto_recovery = self.cfg.get("auto_recovery", {}) or {}
        failures = []
        warnings = []
        if broker.get("environment") == "live":
            failures.append("broker.environment is live; V1.0 should run in testnet/demo only.")
        if safety.get("allow_live_trading", False):
            failures.append("broker.safety.allow_live_trading is true; this is blocked for V1.0 deployment.")
        if not safety.get("default_dry_run", True):
            warnings.append("broker.safety.default_dry_run is false; use explicit testnet confirmation for any execution.")
        if execution.get("execute_demo_orders", False):
            warnings.append("execution.execute_demo_orders is true; keep false unless intentionally testing Demo/Testnet.")
        if auto_recovery.get("enabled", False):
            warnings.append("auto_recovery.enabled is true; verify action whitelist and testnet API keys before running.")
        if failures:
            return CheckResult("safety_config", "fail", "Unsafe trading configuration detected.", {"failures": failures, "warnings": warnings})
        status = "warn" if warnings else "pass"
        return CheckResult("safety_config", status, "Safety configuration checked.", {"warnings": warnings})

    def check_data_and_model_files(self) -> CheckResult:
        data = self.cfg.get("data", {}) or {}
        model = self.cfg.get("model", {}) or {}
        paths = {
            "raw_path": data.get("raw_path"),
            "feature_path": data.get("feature_path"),
            "dataset_path": data.get("dataset_path"),
            "model_path": model.get("model_path"),
            "feature_list_path": model.get("feature_list_path"),
        }
        existence = {name: (None if value is None else self._path(value).exists()) for name, value in paths.items()}
        missing_required_for_signal = [name for name in ["dataset_path", "model_path", "feature_list_path"] if not existence.get(name)]
        if missing_required_for_signal:
            return CheckResult(
                "data_model_files",
                "warn",
                "Some files needed for signal execution are missing; run download/build/train scripts first.",
                {"paths": {k: str(v) for k, v in paths.items()}, "exists": existence, "missing_for_signal": missing_required_for_signal},
            )
        return CheckResult("data_model_files", "pass", "Data/model files needed for signal execution exist.", {"exists": existence})

    def check_database(self) -> CheckResult:
        db_path = self.cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
        path = self._path(db_path)
        try:
            store = PaperStore(path)
            tables = store.paper_tables()
            counts: dict[str, int] = {}
            for t in tables:
                try:
                    counts[t] = len(store.read_table(t))
                except Exception:
                    counts[t] = -1
            return CheckResult("sqlite_database", "pass", "SQLite paper/demo database is accessible and schema is initialized.", {"path": str(path), "row_counts": counts})
        except Exception as exc:
            return CheckResult("sqlite_database", "fail", f"SQLite database check failed: {exc}", {"path": str(path)})

    def check_api_env(self) -> CheckResult:
        broker = self.cfg.get("broker", {}) or {}
        key_env = broker.get("api_key_env", "BINANCE_TESTNET_API_KEY")
        secret_env = broker.get("secret_env", "BINANCE_TESTNET_API_SECRET")
        key_set = bool(os.getenv(str(key_env)))
        secret_set = bool(os.getenv(str(secret_env)))
        mode = (self.cfg.get("execution", {}) or {}).get("mode", "local_paper")
        if mode == "binance_futures_demo" and not (key_set and secret_set):
            return CheckResult(
                "testnet_api_env",
                "warn",
                "Execution mode is binance_futures_demo but testnet API environment variables are incomplete.",
                {"api_key_env": key_env, "api_key_set": key_set, "secret_env": secret_env, "secret_set": secret_set},
            )
        return CheckResult(
            "testnet_api_env",
            "pass" if key_set and secret_set else "info",
            "Testnet API environment variables checked. Local paper mode does not require them.",
            {"api_key_env": key_env, "api_key_set": key_set, "secret_env": secret_env, "secret_set": secret_set},
        )

    def check_disk_space(self) -> CheckResult:
        try:
            usage = os.statvfs(self.root)
            free_bytes = usage.f_bavail * usage.f_frsize
            free_gb = free_bytes / (1024**3)
            status = "warn" if free_gb < 2 else "pass"
            return CheckResult("disk_space", status, f"Free disk space: {free_gb:.2f} GB", {"free_gb": free_gb})
        except Exception as exc:  # pragma: no cover
            return CheckResult("disk_space", "info", f"Disk-space check skipped: {exc}")

    def run(self) -> DeploymentHealthReport:
        checks = [
            self.check_python(),
            self.check_imports(),
            self.check_directories(),
            self.check_safety_config(),
            self.check_data_and_model_files(),
            self.check_database(),
            self.check_api_env(),
            self.check_disk_space(),
        ]
        if any(c.status == "fail" for c in checks):
            overall = "fail"
        elif any(c.status == "warn" for c in checks):
            overall = "warn"
        else:
            overall = "pass"
        return DeploymentHealthReport(timestamp_utc=self._now(), overall_status=overall, project_root=str(self.root), checks=checks)

    def write_report(self, report: DeploymentHealthReport, path: str | Path | None = None) -> Path:
        import json

        if path is None:
            path = self.cfg.get("deployment", {}).get("health_report_path", "reports/deployment/health_report.json")
        out = self._path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2, default=str)
        return out
