from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config
from crypto_quant.paper.ensemble_runner import latest_ensemble_preview


def main() -> None:
    cfg = load_config()
    preview, account, candidates = latest_ensemble_preview(cfg)
    print("ensemble paper preview:")
    for k, v in preview.items():
        print(f"{k}: {v}")
    print("\naccount:")
    print(account)
    print("\nselected candidates:")
    print(candidates.to_string(index=False))


if __name__ == "__main__":
    main()
