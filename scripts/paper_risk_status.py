from __future__ import annotations

import argparse
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Print current local paper account risk/protective-order status.")
    parser.add_argument("--db", default=None, help="Optional custom SQLite database path.")
    args = parser.parse_args()

    cfg = load_config()
    db_path = resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    store = PaperStore(db_path)
    account = store.load_account(
        initial_equity=float(cfg["trading"]["initial_equity"]),
        leverage=float(cfg["trading"]["leverage"]),
    )
    print({
        "db_path": str(db_path),
        "equity": account.equity,
        "cash": account.cash,
        "in_position": account.in_position,
        "position_qty": account.position_qty,
        "entry_price": account.entry_price,
        "bars_held": account.bars_held,
        "stop_loss_price": account.stop_loss_price,
        "take_profit_price": account.take_profit_price,
        "trailing_stop_price": account.trailing_stop_price,
        "highest_price_since_entry": account.highest_price_since_entry,
        "consecutive_losses": account.consecutive_losses,
        "risk_pause_until": account.risk_pause_until,
        "daily_loss_date": account.daily_loss_date,
        "daily_realized_pnl": account.daily_realized_pnl,
    })


if __name__ == "__main__":
    main()
