#!/usr/bin/env python3
# scripts/run_backtest.py

import os
import sys
from datetime import datetime

# ─── FORCE HEADLESS AGG BACKEND ────────────────────────────────────────────────
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)

import backtrader as bt
import matplotlib.pyplot as plt

# ─── PROJECT ROOT ON PATH ──────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles            import load_candles
from strategies.HmaLevelStrategy  import HmaLevelStrategy

# ─── ENSURE RESULTS DIR ─────────────────────────────────────────────────────────
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def run(symbol: str,
        start:  str,
        end:    str,
        fast:   int,
        mid1:   int,
        mid2:   int,
        mid3:   int,
        level:  int,
        atr_mult: float = 0.0):
    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # Load warmup + test data
    df_all = load_candles(symbol, "2025-04-01", end)
    data = bt.feeds.PandasData(
        dataname=df_all,
        timeframe=bt.TimeFrame.Minutes,
        compression=1
    )
    cerebro.adddata(data, name=symbol)

    # Add our level-based HMA strategy
    cerebro.addstrategy(
        HmaLevelStrategy,
        fast=fast,
        mid1=mid1,
        mid2=mid2,
        mid3=mid3,
        level=level,
        atr_mult=atr_mult,
        printlog=True
    )

    strat = cerebro.run()[0]

    # Extract metrics
    sa     = strat.analyzers
    sharpe = sa.sharpe.get_analysis().get("sharperatio", None)
    dd     = sa.drawdown.get_analysis().max.drawdown
    tr     = sa.trades.get_analysis()
    won    = tr.get("won",   {}).get("total", 0)
    lost   = tr.get("lost",  {}).get("total", 0)
    total  = tr.get("total", {}).get("closed", 0)
    winr   = (won / total * 100) if total else 0.0

    print("\n=== Performance Metrics ===")
    print(f"Sharpe Ratio : {sharpe:.2f}" if sharpe is not None else "Sharpe Ratio : N/A")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winr:.1f}% ({won}W/{lost}L)\n")


if __name__ == "__main__":
    # Example: test "bull3" only on ICICIBANK
    run(
        symbol="ICICIBANK",
        start="2025-04-01",
        end="2025-07-06",
        fast=600,
        mid1=760,
        mid2=1040,
        mid3=1520,
        level=3,
        atr_mult=0.0
    )
