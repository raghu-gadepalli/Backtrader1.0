#!/usr/bin/env python3
# scripts/run_hma_old.py

import os
import sys
from datetime import datetime

# headless plotting
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)

import backtrader as bt

# ensure project root on PYTHONPATH
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles            import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

def run_period(symbol: str, start: str, end: str):
    cerebro = bt.Cerebro()
    # add metrics
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # load minute data
    df = load_candles(symbol, start, end)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    # old-strength strategy (direct rec["hma320"], etc.)
    cerebro.addstrategy(HmaStateStrengthStrategy,
                        fast=600, mid1=760, mid2=1040, mid3=1520,
                        atr_mult=0.12, printlog=False)

    strat = cerebro.run()[0]

    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", None)
    dd     = strat.analyzers.drawdown.get_analysis()
    tr     = strat.analyzers.trades.get_analysis()
    won    = tr.get("won",   {}).get("total", 0)
    lost   = tr.get("lost",  {}).get("total", 0)
    total  = tr.get("total", {}).get("closed", 0)
    winr   = won/total*100 if total else 0.0
    maxdd  = dd.max.drawdown

    print(f"Sharpe Ratio : {sharpe:.2f}" if sharpe is not None else "Sharpe Ratio : N/A")
    print(f"Max Drawdown : {maxdd:.2f}%")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winr:.1f}% ({won}W/{lost}L)\n")

if __name__ == "__main__":
    periods = [
        ("2025-05-01", "2025-05-31"),
        ("2025-06-01", "2025-06-30"),
    ]
    for symbol in ("ICICIBANK", "INFY", "RELIANCE"):
        for start, end in periods:
            print(f"--- {symbol} | {start} → {end} ---")
            run_period(symbol, start, end)
