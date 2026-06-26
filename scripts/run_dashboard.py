from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from crypto_quant.config import project_root


def main() -> None:
    app = project_root() / "frontend" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app)]
    print("Starting BTC Quant Research Console...")
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=project_root(), check=False)


if __name__ == "__main__":
    main()
