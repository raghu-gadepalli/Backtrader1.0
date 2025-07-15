#!/usr/bin/env python3
# scripts/run_supertrend_sweep.py

import os
import sys
import csv
import pandas as pd

# headless Matplotlib
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

#  project root 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles     import load_candles
from strategies.supertrend import SuperTrend, ST

#  output CSV 
OUTPUT_CSV = "supertrend_sweep_results.csv"

#  symbols & parameter grid 
SYMBOLS = [
    "AXISBANK", "HDFCBANK", "ICICIBANK", "INFY",
    "KOTAKBANK", "MARUTI", "RELIANCE", "SBIN",
    "SUNPHARMA", "TECHM"
]
PERIODS = [30, 40, 60, 80, 120, 160, 180, 240]
MULTS   = [1.8, 2.0, 2.2, 2.5, 3.0]

#  walkforward windows for tuning 
WINDOWS = [
    {
        "label": "JanFeb",
        "warm":  "2025-01-01",
        "start": "2025-02-01",
        "end":   "2025-02-28",
    },
    {
        "label": "FebMar",
        "warm":  "2025-02-01",
        "start": "2025-03-01",
        "end":   "2025-03-31",
    },
    {
        "label": "MarApr",
        "warm":  "2025-03-01",
        "start": "2025-04-01",
        "end":   "2025-04-30",
    },
]

def run_sweep(symbol, window, period, mult):
    """
    Runs one backtest for given symbol, window, st-period & multiplier.
    Returns a list of results to write to CSV.
    """
    # load warmup + test slice
    df = load_candles(symbol, window["warm"], window["end"])
    df.index = pd.to_datetime(df.index)

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(
        ST,
        st_period=period,
        st_mult=mult
    )

    strat = cerebro.run()[0]
    sr    = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd    = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr    = strat.analyzers.trades.get_analysis()
    won   = tr.get("won",  {}).get("total", 0)
    lost  = tr.get("lost", {}).get("total", 0)
    tot   = tr.get("total",{}).get("closed", 0)
    wr    = (won / tot * 100) if tot else 0.0

    # Console output
    print(f"\n--- {symbol} | {window['label']} @ ST({period},{mult}) "
          f"[warmup {window['warm']}  {window['start']}{window['end']}] ---")
    print(f"Sharpe Ratio : {sr:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {wr:.1f}% ({won}W/{lost}L)")

    # Row for CSV
    return [
        symbol,
        window["label"],
        window["warm"],
        window["start"],
        window["end"],
        period,
        mult,
        f"{sr:.4f}",
        f"{dd:.2f}",
        tot,
        f"{wr:.1f}",
        won,
        lost
    ]

if __name__ == "__main__":
    # Open CSV and write header
    with open(OUTPUT_CSV, "w", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow([
            "symbol",
            "window",
            "warmup",
            "start",
            "end",
            "period",
            "mult",
            "sharpe",
            "drawdown",
            "total_trades",
            "win_rate",
            "won",
            "lost"
        ])

        # Sweep over everything
        for symbol in SYMBOLS:
            for period in PERIODS:
                for mult in MULTS:
                    for win in WINDOWS:
                        row = run_sweep(symbol, win, period, mult)
                        writer.writerow(row)

    print(f"\n  Sweep complete; results saved to {OUTPUT_CSV}")
