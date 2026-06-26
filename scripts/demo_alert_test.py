from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.alerts import AlertMessage, AlertRouter
from crypto_quant.config import load_config, project_root, resolve_path
from crypto_quant.paper.database import PaperStore


def main() -> None:
    cfg = load_config()
    store = PaperStore(resolve_path(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
    router = AlertRouter.from_config(cfg, project_root=project_root())
    result = router.notify(
        AlertMessage(
            level="info",
            title="BTC Quant alert test",
            message="Alert routing is working. This is a local/demo test message.",
            payload={"source": "demo_alert_test.py"},
        )
    )
    store.append_alert(result)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
