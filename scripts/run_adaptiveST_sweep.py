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
BASE_MULTS    = [1.6, 1.7, 1.8, 1.9, 2.0]
VOL_LOOKBACKS = [120, 240, 480]

# ─── test windows (warm‐up for priming + slice for analyzers) ────────────────────
WARMUP = "2025-04-01"
WINDOWS = {
    "May-2025":   ("2025-05-01", "2025-05-31"),
    "June-2025":  ("2025-06-01", "2025-06-30"),
    "July1-2025": ("2025-07-01", "2025-07-14"),
}

# ─── collect results ─────────────────────────────────────────────────────────────
results = []

def run_sweep(symbol, window_label, start, end, base_mult, vol_lb):
    # load warm‑up → end
    df = load_candles(symbol, WARMUP, end)
    df.index = pd.to_datetime(df.index)

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    # feed only the test window to analyzers
    data = bt.feeds.PandasData(
        dataname    = df,
        fromdate    = pd.to_datetime(start),
        todate      = pd.to_datetime(end),
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1,
    )
    cerebro.adddata(data, name=symbol)

    # add the adaptive‐ST strategy
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
    won  = trd.get("won", {}).get("total", 0)
    lost = trd.get("lost", {}).get("total", 0)
    tot  = trd.get("total", {}).get("closed", 0)
    wr   = (won / tot * 100) if tot else 0.0

    print(f"--- {symbol} | {window_label} @ AdaptiveST("
          f"period={ST_PERIOD},base_mult={base_mult},vol_lb={vol_lb}) ---")
    print(f"Sharpe Ratio : {sr:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {wr:.1f}% ({won}W/{lost}L)\n")

    results.append({
        "symbol":        symbol,
        "window":        window_label,
        "start":         start,
        "end":           end,
        "st_period":     ST_PERIOD,
        "base_mult":     base_mult,
        "vol_lookback":  vol_lb,
        "sharpe":        sr,
        "drawdown":      dd,
        "trades":        tot,
        "win_rate":      wr,
    })

if __name__ == "__main__":
    for symbol in SYMBOLS:
        for base_mult in BASE_MULTS:
            for vol_lb in VOL_LOOKBACKS:
                for window_label, (start, end) in WINDOWS.items():
                    run_sweep(symbol, window_label, start, end, base_mult, vol_lb)

    # write out the complete sweep
    pd.DataFrame(results).to_csv("adaptiveST_sweep.csv", index=False)
    print("Wrote adaptiveST_sweep.csv")
