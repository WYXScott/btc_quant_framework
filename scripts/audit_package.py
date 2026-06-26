from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.ui.package_audit import write_package_audit


def main() -> None:
    paths = write_package_audit()
    print(json.dumps({k: str(v) for k, v in paths.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
