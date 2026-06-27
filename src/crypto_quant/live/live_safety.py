from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from crypto_quant.exchange.ccxt_factory import create_ccxt_exchange


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


@dataclass(frozen=True)
class SafetyCheckItem:
    name: str
    status: str  # pass | warn | block
    severity: str  # info | warning | critical
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveGateReport:
    timestamp_utc: str
    status: str  # pass | warn | blocked
    mode: str
    blockers: list[SafetyCheckItem]
    warnings: list[SafetyCheckItem]
    checks: list[SafetyCheckItem]
    config_snapshot: dict[str, Any]

    @property
    def allowed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "status": self.status,
            "mode": self.mode,
            "allowed": self.allowed,
            "blockers": [b.to_dict() for b in self.blockers],
            "warnings": [w.to_dict() for w in self.warnings],
            "checks": [c.to_dict() for c in self.checks],
            "config_snapshot": self.config_snapshot,
        }


class LiveSafetyStore:
    """Small SQLite audit store for live-safety checks.

    It intentionally reuses the paper database path by default so deployment
    diagnostics, pre-trade gates and runtime bundles can inspect one file.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.create_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS live_safety_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT,
                    message TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shadow_live_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    source TEXT NOT NULL,
                    symbol TEXT,
                    equity_usdt REAL,
                    position_qty REAL,
                    open_order_count INTEGER,
                    dry_run INTEGER NOT NULL,
                    payload_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prelive_validation_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    status TEXT NOT NULL,
                    report_path TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def append_event(self, event_type: str, status: str, message: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO live_safety_events(timestamp_utc, event_type, status, message, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (utc_now_iso(), event_type, status, message, json.dumps(payload or {}, ensure_ascii=False, default=str)),
            )

    def append_shadow_snapshot(self, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO shadow_live_snapshots(
                    timestamp_utc, source, symbol, equity_usdt, position_qty, open_order_count, dry_run, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("timestamp_utc") or utc_now_iso()),
                    str(payload.get("source") or "unknown"),
                    payload.get("symbol"),
                    _safe_float(payload.get("equity_usdt"), 0.0),
                    _safe_float(payload.get("position_qty"), 0.0),
                    int(payload.get("open_order_count") or 0),
                    1 if payload.get("dry_run", True) else 0,
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )

    def append_prelive_report(self, payload: dict[str, Any], report_path: str | Path | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO prelive_validation_reports(timestamp_utc, status, report_path, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(payload.get("timestamp_utc") or utc_now_iso()),
                    str(payload.get("status") or "unknown"),
                    None if report_path is None else str(report_path),
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )


class KillSwitch:
    """File-based trading kill switch.

    The kill switch is intentionally independent from the exchange adapter. Any
    future live execution path should read it before constructing orders.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def trigger(self, reason: str = "manual", *, actor: str = "operator") -> dict[str, Any]:
        payload = {
            "enabled": True,
            "reason": reason,
            "actor": actor,
            "timestamp_utc": utc_now_iso(),
        }
        _write_json(self.path, payload)
        return payload

    def clear(self, reason: str = "manual_clear", *, actor: str = "operator") -> dict[str, Any]:
        payload = {
            "enabled": False,
            "reason": reason,
            "actor": actor,
            "timestamp_utc": utc_now_iso(),
        }
        _write_json(self.path, payload)
        return payload

    def status(self) -> dict[str, Any]:
        payload = _read_json(self.path)
        if not payload:
            return {"enabled": False, "path": str(self.path), "reason": "no_kill_switch_file"}
        payload["path"] = str(self.path)
        payload["enabled"] = bool(payload.get("enabled", False))
        return payload

    def is_triggered(self) -> bool:
        return bool(self.status().get("enabled", False))


@dataclass(frozen=True)
class HardCircuitReport:
    timestamp_utc: str
    status: str  # pass | warn | blocked
    current_equity: float
    peak_equity: float
    total_drawdown_fraction: float
    daily_loss_fraction: float
    max_total_drawdown_fraction: float
    max_daily_loss_fraction: float
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HardCircuitBreaker:
    def __init__(self, max_daily_loss_fraction: float, max_total_drawdown_fraction: float):
        self.max_daily_loss_fraction = float(max_daily_loss_fraction)
        self.max_total_drawdown_fraction = float(max_total_drawdown_fraction)

    def evaluate_equity_curve(self, equity_curve: pd.DataFrame) -> HardCircuitReport:
        if equity_curve is None or equity_curve.empty or "equity" not in equity_curve.columns:
            return HardCircuitReport(
                timestamp_utc=utc_now_iso(),
                status="warn",
                current_equity=0.0,
                peak_equity=0.0,
                total_drawdown_fraction=0.0,
                daily_loss_fraction=0.0,
                max_total_drawdown_fraction=self.max_total_drawdown_fraction,
                max_daily_loss_fraction=self.max_daily_loss_fraction,
                message="No equity curve available; hard circuit cannot verify realized risk.",
            )
        df = equity_curve.copy()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
            df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
        equity = pd.to_numeric(df["equity"], errors="coerce").dropna()
        if equity.empty:
            return HardCircuitReport(
                timestamp_utc=utc_now_iso(),
                status="warn",
                current_equity=0.0,
                peak_equity=0.0,
                total_drawdown_fraction=0.0,
                daily_loss_fraction=0.0,
                max_total_drawdown_fraction=self.max_total_drawdown_fraction,
                max_daily_loss_fraction=self.max_daily_loss_fraction,
                message="Equity curve contains no numeric equity values.",
            )
        current = float(equity.iloc[-1])
        peak = float(equity.cummax().iloc[-1])
        total_dd = 0.0 if peak <= 0 else (current / peak - 1.0)
        daily_loss = 0.0
        if "timestamp" in df.columns and not df["timestamp"].isna().all():
            last_day = df["timestamp"].iloc[-1].date()
            day_df = df[df["timestamp"].dt.date == last_day]
            if not day_df.empty:
                first_day_equity = _safe_float(day_df["equity"].iloc[0], current)
                if first_day_equity > 0:
                    daily_loss = current / first_day_equity - 1.0
        status = "pass"
        message = "Hard circuit limits are not breached."
        if total_dd <= -abs(self.max_total_drawdown_fraction):
            status = "blocked"
            message = "Total drawdown hard circuit is breached."
        if daily_loss <= -abs(self.max_daily_loss_fraction):
            status = "blocked"
            message = "Daily loss hard circuit is breached."
        return HardCircuitReport(
            timestamp_utc=utc_now_iso(),
            status=status,
            current_equity=current,
            peak_equity=peak,
            total_drawdown_fraction=total_dd,
            daily_loss_fraction=daily_loss,
            max_total_drawdown_fraction=self.max_total_drawdown_fraction,
            max_daily_loss_fraction=self.max_daily_loss_fraction,
            message=message,
        )


class ShadowLiveReadOnlyClient:
    """Read-only live-account inspection helper.

    This class never calls create_order/cancel_order/set_leverage. It only fetches
    balance, positions, open orders and ticker data when explicitly requested.
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.shadow_cfg = cfg.get("shadow_live", {})

    def _live_cfg(self) -> dict[str, Any]:
        cfg = json.loads(json.dumps(self.cfg, default=str))
        cfg.setdefault("broker", {})
        cfg["broker"]["environment"] = "live"
        cfg["broker"]["api_key_env"] = self.shadow_cfg.get("api_key_env", "BINANCE_LIVE_READONLY_API_KEY")
        cfg["broker"]["secret_env"] = self.shadow_cfg.get("secret_env", "BINANCE_LIVE_READONLY_API_SECRET")
        cfg.setdefault("exchange", {})
        cfg["exchange"]["testnet"] = False
        return cfg

    def offline_snapshot(self) -> dict[str, Any]:
        return {
            "timestamp_utc": utc_now_iso(),
            "source": "offline_shadow_live_preview",
            "dry_run": True,
            "symbol": self.cfg.get("symbol", {}).get("ccxt_symbol", "BTC/USDT:USDT"),
            "equity_usdt": float(self.cfg.get("trading", {}).get("initial_equity", 1000.0)),
            "position_qty": 0.0,
            "open_order_count": 0,
            "message": "Offline preview only. No live private endpoint was queried.",
            "required_env": {
                "api_key_env": self.shadow_cfg.get("api_key_env", "BINANCE_LIVE_READONLY_API_KEY"),
                "secret_env": self.shadow_cfg.get("secret_env", "BINANCE_LIVE_READONLY_API_SECRET"),
            },
        }

    def fetch_private_snapshot(self) -> dict[str, Any]:
        live_cfg = self._live_cfg()
        exchange = create_ccxt_exchange(live_cfg, require_private=True)
        symbol = str(live_cfg.get("symbol", {}).get("ccxt_symbol", "BTC/USDT:USDT"))
        balance = exchange.fetch_balance()
        positions = exchange.fetch_positions([symbol])
        open_orders = exchange.fetch_open_orders(symbol)
        ticker = exchange.fetch_ticker(symbol)
        selected = None
        raw_symbol = str(live_cfg.get("symbol", {}).get("raw_symbol", "BTCUSDT"))
        for pos in positions or []:
            if pos.get("symbol") == symbol or pos.get("info", {}).get("symbol") == raw_symbol:
                selected = pos
                break
        selected = selected or {"contracts": 0.0, "side": None, "entryPrice": None, "info": {}}
        equity = _extract_usdt_equity(balance, default=float(live_cfg.get("trading", {}).get("initial_equity", 1000.0)))
        return {
            "timestamp_utc": utc_now_iso(),
            "source": "live_readonly_private_snapshot",
            "dry_run": False,
            "symbol": symbol,
            "equity_usdt": equity,
            "position_qty": _safe_float(selected.get("contracts") or selected.get("info", {}).get("positionAmt"), 0.0),
            "position_side": selected.get("side"),
            "entry_price": selected.get("entryPrice"),
            "open_order_count": len(open_orders or []),
            "last_price": ticker.get("last") if isinstance(ticker, dict) else None,
            "raw_position": selected,
            "open_orders": open_orders,
            "balance_keys": sorted(list(balance.keys()))[:20] if isinstance(balance, dict) else [],
        }


def _extract_usdt_equity(balance: dict[str, Any], default: float) -> float:
    candidates: list[Any] = []
    if isinstance(balance.get("total"), dict):
        candidates.append(balance["total"].get("USDT"))
    if isinstance(balance.get("free"), dict):
        candidates.append(balance["free"].get("USDT"))
    info = balance.get("info", {}) if isinstance(balance.get("info"), dict) else {}
    for key in ["totalWalletBalance", "totalMarginBalance", "availableBalance", "totalCrossWalletBalance"]:
        candidates.append(info.get(key))
    assets = info.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if isinstance(asset, dict) and str(asset.get("asset", "")).upper() == "USDT":
                for key in ["marginBalance", "walletBalance", "availableBalance"]:
                    candidates.append(asset.get(key))
    for value in candidates:
        f = _safe_float(value, -1.0)
        if f >= 0:
            return f
    return default


class PreLiveValidationBuilder:
    def __init__(self, cfg: dict[str, Any], *, root: str | Path | None = None):
        self.cfg = cfg
        self.root = Path(root) if root is not None else Path.cwd()
        self.live_cfg = cfg.get("live_trading", {})

    def _resolve(self, path: str | Path) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.root / p

    def _csv_rows(self, path: Path) -> int:
        if not path.exists():
            return 0
        try:
            return len(pd.read_csv(path))
        except Exception:
            return 0

    def build(self) -> dict[str, Any]:
        checks: list[SafetyCheckItem] = []
        min_demo_days = int(self.live_cfg.get("min_demo_validation_days", 30))
        required = self.live_cfg.get("required_reports", {})
        for name, rel_path in required.items():
            path = self._resolve(rel_path)
            exists = path.exists()
            checks.append(SafetyCheckItem(
                name=f"required_report:{name}",
                status="pass" if exists else "block",
                severity="critical" if not exists else "info",
                message=f"{name} report {'exists' if exists else 'is missing'}.",
                details={"path": str(path)},
            ))
        demo_equity_path = self._resolve(self.live_cfg.get("demo_equity_curve_path", "reports/ensemble_paper/ensemble_paper_equity_curve.csv"))
        demo_days = 0
        if demo_equity_path.exists():
            try:
                df = pd.read_csv(demo_equity_path)
                ts_col = "timestamp" if "timestamp" in df.columns else None
                if ts_col:
                    ts = pd.to_datetime(df[ts_col], errors="coerce", utc=True).dropna()
                    if not ts.empty:
                        demo_days = max(1, int((ts.max() - ts.min()).days) + 1)
            except Exception:
                demo_days = 0
        checks.append(SafetyCheckItem(
            name="demo_validation_days",
            status="pass" if demo_days >= min_demo_days else "block",
            severity="critical" if demo_days < min_demo_days else "info",
            message=f"Demo validation days: {demo_days}; required: {min_demo_days}.",
            details={"demo_days": demo_days, "required_days": min_demo_days, "path": str(demo_equity_path)},
        ))
        blockers = [c for c in checks if c.status == "block"]
        warnings = [c for c in checks if c.status == "warn"]
        status = "pass" if not blockers else "blocked"
        return {
            "timestamp_utc": utc_now_iso(),
            "status": status,
            "min_demo_validation_days": min_demo_days,
            "blockers": [b.to_dict() for b in blockers],
            "warnings": [w.to_dict() for w in warnings],
            "checks": [c.to_dict() for c in checks],
        }


class LiveSafetyGate:
    def __init__(self, cfg: dict[str, Any], *, root: str | Path | None = None):
        self.cfg = cfg
        self.root = Path(root) if root is not None else Path.cwd()
        self.live_cfg = cfg.get("live_trading", {})

    def _resolve(self, path: str | Path) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.root / p

    def _paper_store_path(self) -> Path:
        return self._resolve(self.cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))

    def _read_last_prelive_report(self) -> dict[str, Any]:
        path = self._resolve(self.live_cfg.get("prelive_validation_report_path", "reports/prelive_validation/prelive_validation_report.json"))
        return _read_json(path)

    def _read_equity_curve(self) -> pd.DataFrame:
        db_path = self._paper_store_path()
        if not db_path.exists():
            return pd.DataFrame()
        try:
            with sqlite3.connect(db_path) as conn:
                return pd.read_sql_query("SELECT * FROM equity_curve ORDER BY timestamp", conn)
        except Exception:
            return pd.DataFrame()

    def evaluate(self, *, mode: str = "live_order") -> LiveGateReport:
        checks: list[SafetyCheckItem] = []
        broker = self.cfg.get("broker", {})
        safety = broker.get("safety", {})
        live_master = bool(self.live_cfg.get("master_enable", False))
        manual_phrase = str(self.live_cfg.get("manual_confirmation_phrase", "I_ACCEPT_LIVE_TRADING_RISK"))
        kill_switch = KillSwitch(self._resolve(self.live_cfg.get("kill_switch_path", "data/database/KILL_SWITCH.json")))

        checks.append(SafetyCheckItem(
            name="live_master_enable",
            status="pass" if live_master else "block",
            severity="critical",
            message="live_trading.master_enable is enabled." if live_master else "live_trading.master_enable is false; live order execution remains blocked.",
        ))
        checks.append(SafetyCheckItem(
            name="broker_environment_live",
            status="pass" if str(broker.get("environment", "testnet")).lower() == "live" else "block",
            severity="critical",
            message=f"broker.environment={broker.get('environment', 'testnet')!r}.",
        ))
        checks.append(SafetyCheckItem(
            name="broker_allow_live_trading",
            status="pass" if bool(safety.get("allow_live_trading", False)) else "block",
            severity="critical",
            message="broker.safety.allow_live_trading is enabled." if bool(safety.get("allow_live_trading", False)) else "broker.safety.allow_live_trading is false.",
        ))
        checks.append(SafetyCheckItem(
            name="kill_switch",
            status="block" if kill_switch.is_triggered() else "pass",
            severity="critical" if kill_switch.is_triggered() else "info",
            message="Kill switch is triggered." if kill_switch.is_triggered() else "Kill switch is clear.",
            details=kill_switch.status(),
        ))
        max_live_lev = float(self.live_cfg.get("max_live_leverage", 3.0))
        configured_lev = float(self.cfg.get("trading", {}).get("leverage", 0.0))
        checks.append(SafetyCheckItem(
            name="max_live_leverage",
            status="pass" if configured_lev <= max_live_lev else "block",
            severity="critical" if configured_lev > max_live_lev else "info",
            message=f"Configured leverage={configured_lev}; live cap={max_live_lev}.",
        ))
        if not self.live_cfg.get("allow_live_without_prelive_report", False):
            prelive = self._read_last_prelive_report()
            checks.append(SafetyCheckItem(
                name="prelive_validation_report",
                status="pass" if prelive.get("status") == "pass" else "block",
                severity="critical",
                message=f"Pre-live validation report status={prelive.get('status', 'missing')!r}.",
                details={"path": str(self._resolve(self.live_cfg.get("prelive_validation_report_path", "reports/prelive_validation/prelive_validation_report.json")))},
            ))
        if bool(self.live_cfg.get("hard_circuit_enabled", True)):
            breaker = HardCircuitBreaker(
                max_daily_loss_fraction=float(self.live_cfg.get("max_daily_loss_fraction", 0.02)),
                max_total_drawdown_fraction=float(self.live_cfg.get("max_total_drawdown_fraction", 0.10)),
            )
            circuit = breaker.evaluate_equity_curve(self._read_equity_curve())
            checks.append(SafetyCheckItem(
                name="hard_circuit_breaker",
                status="block" if circuit.status == "blocked" else ("warn" if circuit.status == "warn" else "pass"),
                severity="critical" if circuit.status == "blocked" else ("warning" if circuit.status == "warn" else "info"),
                message=circuit.message,
                details=circuit.to_dict(),
            ))
        unresolved_unknown = _count_unresolved_unknown_orders(self._paper_store_path())
        checks.append(SafetyCheckItem(
            name="unknown_order_state",
            status="pass" if unresolved_unknown == 0 else "block",
            severity="critical" if unresolved_unknown else "info",
            message=f"Unresolved unknown order states: {unresolved_unknown}.",
        ))
        checks.append(SafetyCheckItem(
            name="manual_confirmation_phrase_defined",
            status="pass" if len(manual_phrase) >= 12 else "block",
            severity="critical",
            message="Manual live confirmation phrase is defined." if len(manual_phrase) >= 12 else "Manual live confirmation phrase is too short or missing.",
        ))
        blockers = [c for c in checks if c.status == "block"]
        warnings = [c for c in checks if c.status == "warn"]
        status = "blocked" if blockers else ("warn" if warnings else "pass")
        snapshot = {
            "broker_environment": broker.get("environment"),
            "allow_live_trading": safety.get("allow_live_trading"),
            "master_enable": live_master,
            "max_live_leverage": max_live_lev,
            "configured_leverage": configured_lev,
        }
        return LiveGateReport(
            timestamp_utc=utc_now_iso(),
            status=status,
            mode=mode,
            blockers=blockers,
            warnings=warnings,
            checks=checks,
            config_snapshot=snapshot,
        )

    def write_report(self, path: str | Path, *, mode: str = "live_order") -> LiveGateReport:
        report = self.evaluate(mode=mode)
        out = self._resolve(path)
        _write_json(out, report.to_dict())
        db_path = self._paper_store_path()
        try:
            LiveSafetyStore(db_path).append_event("live_gate_check", report.status, f"Live gate status: {report.status}", report.to_dict())
        except Exception:
            pass
        return report


def _count_unresolved_unknown_orders(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exchange_order_lifecycle'")
            if cur.fetchone() is None:
                return 0
            row = conn.execute("SELECT COUNT(*) FROM exchange_order_lifecycle WHERE state='unknown'").fetchone()
            return int(row[0] or 0)
    except Exception:
        return 0
