#!/usr/bin/env python3
# scripts/run_adaptiveST_sweep.py

import os
import sys
import pandas as pd
import backtrader as bt

# headless matplotlib
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)

# ─── project root ───────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles import load_candles
from strategies.adaptive_supertrend import STAdaptive

# ─── symbols & adaptive‐ST grid ─────────────────────────────────────────────────
SYMBOLS       = ["HDFCBANK"]
ST_PERIOD     = 240
BASE_MULTS    = [1.5, 1.6, 1.7, 1.8, 1.9, 2.0]
VOL_LOOKBACKS = [120, 240, 480]

# ─── test windows (each with its own warm‑up) ─────────────────────────────────────
WINDOWS = [
    {"label": "Jan-Jun",  "warm": "2024-12-01", "start": "2025-01-01", "end": "2025-06-30"},
    {"label": "Jan-Feb",  "warm": "2025-01-01", "start": "2025-02-01", "end": "2025-02-28"},
    {"label": "Feb-Mar",  "warm": "2025-02-01", "start": "2025-03-01", "end": "2025-03-31"},
    {"label": "Mar-Apr",  "warm": "2025-03-01", "start": "2025-04-01", "end": "2025-04-30"},
    {"label": "Apr-May",  "warm": "2025-04-01", "start": "2025-05-01", "end": "2025-05-31"},
    {"label": "May-Jun",  "warm": "2025-05-01", "start": "2025-06-01", "end": "2025-06-30"},
    {"label": "Jun-Jul",  "warm": "2025-06-01", "start": "2025-07-01", "end": "2025-07-14"},
]

results = []

def run_sweep(symbol, w):
    df = load_candles(symbol, w["warm"], w["end"])
    df.index = pd.to_datetime(df.index)

    for base_mult in BASE_MULTS:
        for vol_lb in VOL_LOOKBACKS:
            cerebro = bt.Cerebro()
            cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                                timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
            cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

            data = bt.feeds.PandasData(
                dataname    = df,
                fromdate    = pd.to_datetime(w["start"]),
                todate      = pd.to_datetime(w["end"]),
                timeframe   = bt.TimeFrame.Minutes,
                compression = 1,
            )
            cerebro.adddata(data, name=symbol)

            cerebro.addstrategy(
                STAdaptive,
                st_period    = ST_PERIOD,
                base_mult    = base_mult,
                vol_lookback = vol_lb,
            )

            strat = cerebro.run()[0]
            sr   = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
            dd   = strat.analyzers.drawdown.get_analysis().max.drawdown
            trd  = strat.analyzers.trades.get_analysis()
            won  = trd.get("won",  {}).get("total", 0)
            lost = trd.get("lost", {}).get("total", 0)
            tot  = trd.get("total",{}).get("closed", 0)
            wr   = (won / tot * 100) if tot else 0.0

            print(f"--- {symbol} | {w['label']} @ AdaptiveST("
                  f"period={ST_PERIOD},base_mult={base_mult},vol_lb={vol_lb}) ---")
            print(f"Sharpe Ratio : {sr:.2f}")
            print(f"Max Drawdown : {dd:.2f}%")
            print(f"Total Trades : {tot}")
            print(f"Win Rate     : {wr:.1f}% ({won}W/{lost}L)\n")

            results.append({
                "symbol":       symbol,
                "window":       w["label"],
                "warm":         w["warm"],
                "start":        w["start"],
                "end":          w["end"],
                "st_period":    ST_PERIOD,
                "base_mult":    base_mult,
                "vol_lookback": vol_lb,
                "sharpe":       sr,
                "drawdown":     dd,
                "trades":       tot,
                "win_rate":     wr,
            })

if __name__ == "__main__":
    for symbol in SYMBOLS:
        for w in WINDOWS:
            run_sweep(symbol, w)

    pd.DataFrame(results).to_csv("adaptiveST_sweep.csv", index=False)
    print("Wrote adaptiveST_sweep.csv")
