#!/usr/bin/env python3
# scripts/optimize_hma.py

import os
import sys

#  HEADLESS PLOTTING SETUP 
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)

import backtrader as bt
import pandas as pd

#  PROJECT PATH 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles           import load_candles
from strategies.HmaTrendStrategy import HmaTrendStrategy

#  SETTINGS 
SYMBOL      = "INFY"
START       = "2025-04-01"
END         = "2025-07-06"
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Define your fast periods and derive the matching slow = int(fast * ratio)
fast_vals = [200, 400, 600, 800, 1000]
ratio     = 3.3
combos    = [(f, int(f * ratio)) for f in fast_vals]

#  RUN OPTIMIZATION 
def optimize():
    records = []

    # Pre-load data once
    df = load_candles(SYMBOL, START, END)
    feed = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=1
    )

    for fast, slow in combos:
        cerebro = bt.Cerebro()

        # Add analyzers
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
        cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

        # Add data & strategy
        cerebro.adddata(feed, name=SYMBOL)
        cerebro.addstrategy(
            HmaTrendStrategy,
            fast=fast,
            slow=slow,
            printlog=False
        )

        # Run
        strat = cerebro.run()[0]

        # Extract metrics
        sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", float("nan"))
        dd     = strat.analyzers.drawdown.get_analysis().max.drawdown
        tr     = strat.analyzers.trades.get_analysis()
        total  = tr.total.closed
        won    = tr.won.total
        winpct = won / total * 100 if total else 0.0

        records.append({
            "fast":   fast,
            "slow":   slow,
            "sharpe": round(sharpe, 4),
            "max_dd": round(dd,     4),
            "trades": total,
            "win%":   round(winpct, 1),
        })

        print(f"Tested fast={fast:<4} slow={slow:<4}  Sharpe={sharpe:.4f}, Win%={winpct:.1f}%")

    # Build DataFrame
    df_res = pd.DataFrame(records)
    df_res = df_res.sort_values("sharpe", ascending=False).reset_index(drop=True)

    # Save to CSV
    csv_path = os.path.join(RESULTS_DIR, "hma_optimization_results.csv")
    df_res.to_csv(csv_path, index=False)

    # Print summary
    print("\nTop 5 valid HMA combinations by Sharpe:\n")
    print(df_res.head(5).to_string(index=False))
    print(f"\nFull results saved to {csv_path}")

if __name__ == "__main__":
    optimize()
