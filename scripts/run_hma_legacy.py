#!/usr/bin/env python3
# scripts/run_hma_legacy.py

import os
import sys
from datetime import datetime

# use non-interactive Agg backend
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import backtrader as bt

# add project root to path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def run(symbol: str, start: str, end: str,
        fast: int, mid1: int, mid2: int, mid3: int,
        atr_mult: float = 0.0):

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # warm-up + test
    WARMUP_START = "2025-04-01"
    df = load_candles(symbol, WARMUP_START, end)
    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=1,
    )
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(
        HmaStateStrengthStrategy,
        fast=fast,
        mid1=mid1,
        mid2=mid2,
        mid3=mid3,
        atr_mult=atr_mult,
        printlog=False
    )

    strat = cerebro.run()[0]

    # metrics
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", None)
    dd     = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr     = strat.analyzers.trades.get_analysis()
    won    = tr.get("won", {}).get("total", 0)
    lost   = tr.get("lost", {}).get("total", 0)
    total  = tr.get("total", {}).get("closed", 0)
    winr   = won/total*100 if total else 0.0

    print(f"Sharpe Ratio : {sharpe:.2f}" if sharpe is not None else "Sharpe Ratio : N/A")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winr:.1f}% ({won}W/{lost}L)\n")

if __name__ == "__main__":
    symbols = ["ICICIBANK", "INFY", "RELIANCE"]
    periods = [
        ("2025-05-01", "2025-05-31"),
        ("2025-06-01", "2025-06-30"),
    ]
    # legacy HMA lengths
    LEGACY_PARAMS = dict(
        fast     = 4,      # HMA(4) instead of HMA(1)
        mid1     = 320,    # HMA(320)
        mid2     = 1200,   # HMA(1200)
        mid3     = 3800,   # HMA(3800)
        atr_mult = 0.0,    # no ATR noise-gate
    )

    for sym in symbols:
        for start, end in periods:
            print(f"--- {sym} | {start} → {end} ---")
            run(
                symbol=sym,
                start=start,
                end=end,
                **LEGACY_PARAMS
            )
