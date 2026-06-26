from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config
from crypto_quant.exchange.user_stream import BinanceFuturesUserDataStream


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or create a Binance USD-M Futures user-data stream listen key.")
    parser.add_argument("--execute", action="store_true", help="Actually request a listen key from Demo/Testnet. Requires API keys.")
    parser.add_argument("--confirm", default=None, help="Required confirmation phrase when --execute is used.")
    parser.add_argument("--keepalive", default=None, help="Preview/send listen-key keepalive for the supplied listen key.")
    parser.add_argument("--close", default=None, help="Preview/close the supplied listen key.")
    args = parser.parse_args()

    cfg = load_config()
    stream = BinanceFuturesUserDataStream(cfg, require_private=args.execute)

    if args.keepalive:
        payload = stream.keepalive_listen_key(args.keepalive, execute=args.execute, confirmation=args.confirm)
    elif args.close:
        payload = stream.close_listen_key(args.close, execute=args.execute, confirmation=args.confirm)
    else:
        payload = stream.create_listen_key(execute=args.execute, confirmation=args.confirm).to_dict()

    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
