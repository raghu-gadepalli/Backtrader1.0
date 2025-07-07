#!/usr/bin/env python3
# scripts/run_backtest.py

import os
import sys
import matplotlib
matplotlib.use('Agg')

import backtrader as bt

# ensure project root is on sys.path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles        import load_candles
from strategies.HmaTrendStrategy import HmaTrendStrategy

def run(symbol: str,
        start:  str,
        end:    str,
        fast:   int,
        slow:   int):

    cerebro = bt.Cerebro()

    # 1) load data
    df = load_candles(symbol, start, end)

    # 2) wrap it as a Backtrader feed
    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=1
    )
    cerebro.adddata(data, name=symbol)

    # 3) add our skeleton strategy with the chosen HMA lengths
    cerebro.addstrategy(HmaTrendStrategy, fast=fast, slow=slow)

    # 4) run & plot
    cerebro.run()
    cerebro.plot()

if __name__ == "__main__":
    # adjust these to your test symbol and date range
    run(
        symbol="INFY",
        start="2025-04-01",
        end="2025-07-06",
        fast=2000,
        slow=600
    )
