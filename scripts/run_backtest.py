#!/usr/bin/env python3
# scripts/run_backtest.py

import os
import sys

# ─── FORCE AGG BACKEND ─────────────────────────────────────────────────────────
# Must be done before importing Backtrader or pyplot
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)

import backtrader as bt

# ─── SETUP PROJECT PATH ─────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles           import load_candles
from strategies.HmaTrendStrategy import HmaTrendStrategy

# ─── ENSURE RESULTS DIR ─────────────────────────────────────────────────────────
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def run(symbol: str,
        start:  str,
        end:    str,
        fast:   int,
        slow:   int):

    cerebro = bt.Cerebro()

    # 1) Load data
    df = load_candles(symbol, start, end)

    # 2) Wrap as a Backtrader feed
    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=1
    )
    cerebro.adddata(data, name=symbol)

    # 3) Add strategy
    cerebro.addstrategy(HmaTrendStrategy, fast=fast, slow=slow)

    # 4) Run
    _ = cerebro.run()

    # 5) Plot & save figures
    # cerebro.plot() returns a list of lists of matplotlib.Figure
    all_figs = cerebro.plot()[0]
    for idx, fig in enumerate(all_figs):
        fname = f"{symbol}_hma_fast{fast}_slow{slow}_{idx}.png"
        out_path = os.path.join(RESULTS_DIR, fname)
        fig.savefig(out_path)
        print(f"Saved plot: {out_path}")


if __name__ == "__main__":
    run(
        symbol="INFY",
        start="2025-04-01",
        end="2025-07-06",
        fast=2000,
        slow=600
    )
