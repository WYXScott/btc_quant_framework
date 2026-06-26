from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config
from crypto_quant.exchange.retry import RetryExecutor, RetryPolicy


class TemporaryExchangeError(RuntimeError):
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline retry-policy smoke demo; no exchange connection is made.")
    parser.add_argument("--failures-before-success", type=int, default=2)
    args = parser.parse_args()

    cfg = load_config()
    policy = RetryPolicy.from_config(cfg)
    counter = {"n": 0}

    def flaky_call() -> dict:
        counter["n"] += 1
        if counter["n"] <= args.failures_before_success:
            raise TemporaryExchangeError("temporary network timeout while submitting order")
        return {"ok": True, "attempt": counter["n"]}

    result = RetryExecutor(policy).run(flaky_call)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
