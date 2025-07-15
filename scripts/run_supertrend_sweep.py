#!/usr/bin/env python3
# scripts/run_supertrend_sweep.py

import os
import sys
import csv
import pandas as pd

# headless Matplotlib
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)

import backtrader as bt

# ensure project root on path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles     import load_candles
from strategies.supertrend import ST

# output CSV file
OUTPUT_CSV = "supertrend_sweep_results.csv"

# symbols and parameter grid
SYMBOLS = [
    "AXISBANK", "HDFCBANK", "ICICIBANK", "INFY",
    "KOTAKBANK", "MARUTI", "RELIANCE", "SBIN",
    "SUNPHARMA", "TECHM"
]
PERIODS = [30, 40, 60, 80, 120, 160, 180, 240]
MULTS   = [1.8, 2.0, 2.2, 2.5, 3.0]

# walk‑forward windows for tuning
WINDOWS = [
    {
        "label": "Jan-Feb",
        "warm":  "2025-01-01",
        "start": "2025-02-01",
        "end":   "2025-02-28",
    },
    {
        "label": "Feb-Mar",
        "warm":  "2025-02-01",
        "start": "2025-03-01",
        "end":   "2025-03-31",
    },
    {
        "label": "Mar-Apr",
        "warm":  "2025-03-01",
        "start": "2025-04-01",
        "end":   "2025-04-30",
    },
]

def run_sweep(symbol, window, period, mult):
    # load warm-up through end
    df = load_candles(symbol, window["warm"], window["end"])
    df.index = pd.to_datetime(df.index)

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=1
    )
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

    # print to console
    print()
    print("--- {} | {} @ ST({}, {})".format(
        symbol,
        window["label"],
        period,
        mult
    ))
    print("  warm-up: {}   test: {} to {}".format(
        window["warm"],
        window["start"],
        window["end"]
    ))
    print("Sharpe Ratio : {:.4f}".format(sr))
    print("Max Drawdown : {:.2f}%".format(dd))
    print("Total Trades : {}".format(tot))
    print("Win Rate     : {:.1f}% ({}W/{}L)".format(wr, won, lost))

    # return row for CSV
    return [
        symbol,
        window["label"],
        window["warm"],
        window["start"],
        window["end"],
        period,
        mult,
        "{:.4f}".format(sr),
        "{:.2f}".format(dd),
        tot,
        "{:.1f}".format(wr),
        won,
        lost
    ]

if __name__ == "__main__":
    # open output CSV and write header
    with open(OUTPUT_CSV, "w", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow([
            "symbol", "window", "warmup", "start", "end",
            "period", "mult", "sharpe", "drawdown",
            "total_trades", "win_rate", "won", "lost"
        ])

        # sweep through all combinations
        for symbol in SYMBOLS:
            for period in PERIODS:
                for mult in MULTS:
                    for win in WINDOWS:
                        row = run_sweep(symbol, win, period, mult)
                        writer.writerow(row)

    print()
    print("Sweep complete; results saved to {}".format(OUTPUT_CSV))
