from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import _bootstrap  # noqa: F401

from crypto_quant.config import project_root
from crypto_quant.utils.runtime_env import running_in_project_venv


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the Streamlit BTC Quant Research Console.")
    parser.add_argument("--host", default="localhost", help="Streamlit bind address. Default: localhost")
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port. Default: 8501")
    parser.add_argument("--open-browser", action="store_true", help="Open the dashboard URL in the default browser.")
    parser.add_argument("--no-browser", action="store_true", help="Ask Streamlit not to open a browser automatically.")
    parser.add_argument("--browser-delay", type=float, default=1.5, help="Delay before opening browser when --open-browser is used.")
    return parser


def _streamlit_available() -> bool:
    return importlib.util.find_spec("streamlit") is not None


def _open_browser_later(url: str, delay: float) -> None:
    def _target() -> None:
        time.sleep(max(0.0, delay))
        webbrowser.open(url)

    threading.Thread(target=_target, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = project_root()
    app = root / "frontend" / "app.py"
    url = f"http://{args.host}:{args.port}"

    print("Starting BTC Quant Research Console...")
    print(f"Project: {root}")
    print(f"Python: {Path(sys.executable).resolve()}")
    print(f"Project .venv active: {running_in_project_venv(root)}")
    print(f"URL: {url}")

    if not app.exists():
        print(f"ERROR: Streamlit app is missing: {app}", file=sys.stderr)
        return 2

    if not _streamlit_available():
        print(
            "ERROR: streamlit is not importable. Activate .venv and run: "
            "python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 2

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.address",
        str(args.host),
        "--server.port",
        str(args.port),
    ]
    if args.no_browser:
        cmd.extend(["--server.headless", "true"])
    elif args.open_browser:
        # Keep browser opening explicit so the .cmd launcher can work from
        # PowerShell without relying on a signed .ps1 file. Headless=true
        # prevents Streamlit from opening a duplicate browser tab.
        cmd.extend(["--server.headless", "true"])
        _open_browser_later(url, args.browser_delay)

    print("Command:")
    print(" ".join(str(part) for part in cmd))
    completed = subprocess.run(cmd, cwd=root, env=env, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
