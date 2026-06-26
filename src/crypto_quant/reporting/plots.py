from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from crypto_quant.backtest.metrics import drawdown_series


def plot_equity_curve(result: pd.DataFrame, path: str | Path, title: str = "Equity Curve") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(10, 5))
    ax = fig.add_subplot(111)
    result["equity"].plot(ax=ax)
    ax.set_title(title)
    ax.set_xlabel("Time")
    ax.set_ylabel("Equity")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_drawdown(result: pd.DataFrame, path: str | Path, title: str = "Drawdown") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(10, 4))
    ax = fig.add_subplot(111)
    drawdown_series(result["equity"]).plot(ax=ax)
    ax.set_title(title)
    ax.set_xlabel("Time")
    ax.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
