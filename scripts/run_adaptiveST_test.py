#!/usr/bin/env python3
# scripts/run_adaptiveST_test.py

import os
import sys
import pandas as pd

# headless plotting
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

# ─── project root ───────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles import load_candles
from strategies.adaptive_supertrend import STAdaptive

# Adaptive SuperTrend parameters per symbol
ST_PARAMS = {
    "HDFCBANK": dict(
        st_period    = 240,
        base_mult    = 1.8,
        vol_lookback = 240,
    ),
}

SYMBOLS = list(ST_PARAMS.keys())

# warm‑up for indicator priming
WARMUP = "2025-04-01"

# explicit evaluation windows with clear labels
PERIODS = {
    "May-2025":   ("2025-05-01", "2025-05-31"),
    "June-2025":  ("2025-06-01", "2025-06-30"),
    "July1-2025": ("2025-07-01", "2025-07-14"),
}

# collect test results
results = []

def run_period(symbol, label, start, end):
    params = ST_PARAMS[symbol]
    df = load_candles(symbol, WARMUP, end)
    df.index = pd.to_datetime(df.index)

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes,
                        riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    data = bt.feeds.PandasData(
        dataname    = df,
        fromdate    = pd.to_datetime(start),
        todate      = pd.to_datetime(end),
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1,
    )
    cerebro.adddata(data, name=symbol)

    # Pass the correct param names here:
    cerebro.addstrategy(
        STAdaptive,
        st_period    = params["st_period"],
        base_mult    = params["base_mult"],
        vol_lookback = params["vol_lookback"],
    )

    strat = cerebro.run()[0]
    sharpe  = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd      = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr      = strat.analyzers.trades.get_analysis()
    won     = tr.get("won",  {}).get("total", 0)
    lost    = tr.get("lost", {}).get("total", 0)
    tot     = tr.get("total",{}).get("closed", 0)
    winrate = (won / tot * 100) if tot else 0.0

    print(f"\n--- {symbol} | {label} @ AdaptiveST("
          f"st_period={params['st_period']},"
          f"base_mult={params['base_mult']},"
          f"vol_lookback={params['vol_lookback']}) ---")
    print(f"Sharpe Ratio : {sharpe:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {winrate:.1f}% ({won}W/{lost}L)")

    results.append({
        "symbol":       symbol,
        "period_label": label,
        "start":        start,
        "end":          end,
        "st_period":    params["st_period"],
        "base_mult":    params["base_mult"],
        "vol_lookback": params["vol_lookback"],
        "sharpe":       sharpe,
        "drawdown":     dd,
        "trades":       tot,
        "win_rate":     winrate,
    })

if __name__ == "__main__":
    for sym in SYMBOLS:
        for label, (start, end) in PERIODS.items():
            run_period(sym, label, start, end)

    pd.DataFrame(results).to_csv("adaptive_supertrend_test_results.csv", index=False)
    print("\nWrote adaptive_supertrend_test_results.csv")
