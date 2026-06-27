from __future__ import annotations

from dataclasses import asdict, dataclass, field
import random
import time
from typing import Any, Callable, Generic, TypeVar

from crypto_quant.exchange.errors import ClassifiedExchangeError, classify_exchange_exception

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    jitter_seconds: float = 0.25
    sleep_enabled: bool = False
    retry_categories: tuple[str, ...] = (
        "network_error",
        "rate_limited",
        "exchange_not_available",
        "request_timeout",
        "temporary_exchange_error",
        "unknown_order_state",
    )

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "RetryPolicy":
        retry_cfg = cfg.get("exchange_resilience", {}).get("retry", {})
        return cls(
            max_attempts=int(retry_cfg.get("max_attempts", 3)),
            base_delay_seconds=float(retry_cfg.get("base_delay_seconds", 0.5)),
            max_delay_seconds=float(retry_cfg.get("max_delay_seconds", 8.0)),
            jitter_seconds=float(retry_cfg.get("jitter_seconds", 0.25)),
            sleep_enabled=bool(retry_cfg.get("sleep_enabled", False)),
            retry_categories=tuple(retry_cfg.get("retry_categories", cls.retry_categories)),
        )

    def delay_for_attempt(self, attempt: int) -> float:
        raw = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** max(0, attempt - 1)))
        if self.jitter_seconds > 0:
            raw += random.uniform(0.0, self.jitter_seconds)
        return max(0.0, raw)


@dataclass(frozen=True)
class RetryAttempt:
    attempt: int
    status: str
    retryable: bool
    delay_seconds: float
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetryResult(Generic[T]):
    status: str
    attempts: list[RetryAttempt]
    value: T | None = None
    error: ClassifiedExchangeError | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "attempts": [a.to_dict() for a in self.attempts],
            "value": self.value,
            "error": None if self.error is None else self.error.to_dict(),
        }


class RetryExecutor:
    def __init__(self, policy: RetryPolicy):
        self.policy = policy

    def run(self, func: Callable[[], T]) -> RetryResult[T]:
        attempts: list[RetryAttempt] = []
        last_error: ClassifiedExchangeError | None = None
        for attempt in range(1, max(1, self.policy.max_attempts) + 1):
            try:
                value = func()
                attempts.append(RetryAttempt(attempt=attempt, status="success", retryable=False, delay_seconds=0.0))
                return RetryResult(status="success", attempts=attempts, value=value, error=None)
            except BaseException as exc:  # classify and decide whether to retry
                classified = classify_exchange_exception(exc)
                last_error = classified
                should_retry = classified.retryable and classified.category in self.policy.retry_categories
                is_last = attempt >= self.policy.max_attempts
                delay = 0.0 if (not should_retry or is_last) else self.policy.delay_for_attempt(attempt)
                attempts.append(
                    RetryAttempt(
                        attempt=attempt,
                        status="failed",
                        retryable=bool(should_retry and not is_last),
                        delay_seconds=delay,
                        error=classified.to_dict(),
                    )
                )
                if not should_retry or is_last:
                    return RetryResult(status="failed", attempts=attempts, value=None, error=classified)
                if self.policy.sleep_enabled and delay > 0:
                    time.sleep(delay)
        return RetryResult(status="failed", attempts=attempts, value=None, error=last_error)
