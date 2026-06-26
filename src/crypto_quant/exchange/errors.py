from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ClassifiedExchangeError:
    """Normalized error record for exchange/network/API failures.

    The object is intentionally small and JSON-friendly so it can be persisted
    in SQLite and shown in deployment reports without carrying raw exception
    objects around.
    """

    category: str
    retryable: bool
    severity: str
    message: str
    exception_type: str
    exchange_error_code: str | None = None
    raw: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_RETRYABLE_CATEGORIES = {
    "network_error",
    "rate_limited",
    "exchange_not_available",
    "request_timeout",
    "temporary_exchange_error",
    "unknown_order_state",
}

_NON_RETRYABLE_CATEGORIES = {
    "authentication_error",
    "permission_error",
    "insufficient_funds",
    "invalid_order",
    "order_not_found",
    "precision_error",
    "safety_block",
}


def _safe_getattr(obj: Any, name: str) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return None


def extract_exchange_error_code(exc: BaseException) -> str | None:
    """Best-effort extraction of an exchange numeric/string error code."""
    for attr in ("code", "error_code", "status_code"):
        value = _safe_getattr(exc, attr)
        if value is not None:
            return str(value)
    args = getattr(exc, "args", ())
    if args:
        first = args[0]
        if isinstance(first, dict):
            for key in ("code", "errorCode", "status", "error"):
                if key in first:
                    return str(first[key])
        text = str(first)
    else:
        text = str(exc)
    # Common Binance/CCXT text shape contains e.g. "code":-2019.
    import re

    m = re.search(r'"?code"?\s*[:=]\s*([\-\d]+)', text)
    if m:
        return m.group(1)
    m = re.search(r'\b(-20\d{2}|-10\d{2}|4\d{2}|5\d{2})\b', text)
    if m:
        return m.group(1)
    return None


def classify_exchange_exception(exc: BaseException) -> ClassifiedExchangeError:
    """Classify CCXT and generic exceptions into retry/safety categories.

    This function avoids hard dependency on concrete CCXT classes at import
    time; when ccxt is installed it checks class inheritance, otherwise it falls
    back to names and message patterns. This keeps dry-run/offline scripts usable.
    """
    exc_type = type(exc).__name__
    message = str(exc)
    lower = message.lower()
    code = extract_exchange_error_code(exc)

    # Safety guard exceptions raised by this project.
    if isinstance(exc, PermissionError):
        return ClassifiedExchangeError(
            category="safety_block",
            retryable=False,
            severity="critical",
            message=message,
            exception_type=exc_type,
            exchange_error_code=code,
            raw=repr(exc),
        )
    if isinstance(exc, (ValueError, TypeError)):
        return ClassifiedExchangeError(
            category="invalid_order",
            retryable=False,
            severity="critical",
            message=message,
            exception_type=exc_type,
            exchange_error_code=code,
            raw=repr(exc),
        )

    # Optional CCXT-aware classification.
    try:
        import ccxt  # type: ignore

        if isinstance(exc, getattr(ccxt, "AuthenticationError")):
            category = "authentication_error"
        elif isinstance(exc, getattr(ccxt, "PermissionDenied")):
            category = "permission_error"
        elif isinstance(exc, getattr(ccxt, "InsufficientFunds")):
            category = "insufficient_funds"
        elif isinstance(exc, getattr(ccxt, "InvalidOrder")):
            category = "invalid_order"
        elif isinstance(exc, getattr(ccxt, "OrderNotFound")):
            category = "order_not_found"
        elif isinstance(exc, getattr(ccxt, "RateLimitExceeded")):
            category = "rate_limited"
        elif isinstance(exc, getattr(ccxt, "RequestTimeout")):
            category = "request_timeout"
        elif isinstance(exc, getattr(ccxt, "ExchangeNotAvailable")):
            category = "exchange_not_available"
        elif isinstance(exc, getattr(ccxt, "NetworkError")):
            category = "network_error"
        elif isinstance(exc, getattr(ccxt, "ExchangeError")):
            category = "temporary_exchange_error"
        else:
            category = "unknown_exchange_error"
    except Exception:
        category = "unknown_exchange_error"

    # Message/code overrides for common exchange conditions.
    if code in {"-2019", "-2027"} or "insufficient" in lower or "margin is insufficient" in lower:
        category = "insufficient_funds"
    elif code in {"-1013", "-1111", "-4003"} or "precision" in lower or "filter failure" in lower:
        category = "precision_error"
    elif code in {"-2011", "-2013"} or "order does not exist" in lower or "unknown order" in lower:
        category = "order_not_found"
    elif code in {"-1021", "-1007"} or "timeout" in lower:
        category = "request_timeout"
    elif code in {"-1003"} or "rate limit" in lower or "too many requests" in lower:
        category = "rate_limited"
    elif "connection" in lower or "network" in lower or "temporarily unavailable" in lower:
        category = "network_error"

    retryable = category in _RETRYABLE_CATEGORIES
    if category in _NON_RETRYABLE_CATEGORIES:
        retryable = False
    severity = "warning" if retryable else "critical"
    return ClassifiedExchangeError(
        category=category,
        retryable=retryable,
        severity=severity,
        message=message,
        exception_type=exc_type,
        exchange_error_code=code,
        raw=repr(exc),
    )
