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
SYMBOL     = "INFY"
START      = "2025-04-01"
END        = "2025-07-06"
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Define your grid of fast & slow periods (keeping ~3.3 ratio)
fast_vals = [200, 400, 600, 800, 1000]
slow_vals = [int(f * 3.3)       for f in fast_vals]

#  RUN OPTIMIZATION 
def optimize():
    cerebro = bt.Cerebro(maxcpus=4)
    cerebro.optstrategy(
        HmaTrendStrategy,
        fast=fast_vals,
        slow=slow_vals,
        printlog=False
    )
    # Add analyzers to each run
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # Load data once and add to cerebro
    df = load_candles(SYMBOL, START, END)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=SYMBOL)

    print(f"Running optimization on {len(fast_vals)*len(slow_vals)} combos...")
    runs = cerebro.run()

    records = []
    for run_list in runs:
        strat = run_list[0]  # single-strategy list
        p = strat.params
        sa = strat.analyzers

        sharpe = sa.sharpe.get_analysis().get("sharperatio", float("nan"))
        dd     = sa.drawdown.get_analysis().max.drawdown
        tr     = sa.trades.get_analysis()
        total  = tr.total.closed
        won    = tr.won.total
        winrate = won / total * 100 if total else 0.0

        records.append({
            "fast":   p.fast,
            "slow":   p.slow,
            "sharpe": sharpe,
            "max_dd": dd,
            "trades": total,
            "win%":   round(winrate,1),
        })

    # Build DataFrame
    df_res = pd.DataFrame(records)
    df_res = df_res.sort_values("sharpe", ascending=False).reset_index(drop=True)

    # Save to CSV
    csv_path = os.path.join(RESULTS_DIR, "hma_optimization_results.csv")
    df_res.to_csv(csv_path, index=False)

    # Print the top 10
    print("\nTop 10 HMA combinations by Sharpe:\n")
    print(df_res.head(10).to_string(index=False))
    print(f"\nFull results saved to {csv_path}")

if __name__ == "__main__":
    optimize()
