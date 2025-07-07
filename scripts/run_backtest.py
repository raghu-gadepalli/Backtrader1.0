#!/usr/bin/env python3
# scripts/run_backtest.py

import os
import sys

# ─── FORCE AGG BACKEND ─────────────────────────────────────────────────────────
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

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
    strat_list = cerebro.run()
    strat = strat_list[0]

    # 5) Extract the plotted lines from the strategy
    #    Backtrader stores the indicator values in .lines.array
    data0 = strat.datas[0]
    dates     = [bt.num2date(x) for x in data0.datetime.array]
    close_arr = data0.close.array
    hma_f     = strat.hma_fast.array
    hma_s     = strat.hma_slow.array

    # 6) Manual Matplotlib plot
    plt.figure(figsize=(12, 6))
    plt.plot(dates, close_arr, label="Close", linewidth=1)
    plt.plot(dates, hma_f,     label=f"HMA Fast ({fast})", linewidth=1)
    plt.plot(dates, hma_s,     label=f"HMA Slow ({slow})", linewidth=1)
    plt.title(f"{symbol} Close vs HMA Fast/Slow")
    plt.xlabel("Time")
    plt.ylabel("Price")
    plt.legend()
    plt.tight_layout()

    # 7) Save figure
    fname = f"{symbol}_hma_fast{fast}_slow{slow}.png"
    out_path = os.path.join(RESULTS_DIR, fname)
    plt.savefig(out_path)
    plt.close()
    print(f"Saved plot: {out_path}")


if __name__ == "__main__":
    run(
        symbol="INFY",
        start="2025-04-01",
        end="2025-07-06",
        fast=2000,
        slow=600
    )
