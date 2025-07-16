#!/usr/bin/env python3
# scripts/run_renkoemacr.py

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
from strategies.renko_ema_crossover import RenkoEMAStrategy

# Renko EMA Crossover parameters per symbol
RENKO_EMA_PARAMS = {
    "KOTAKBANK": dict(fast_period=26, slow_period=65, renko_brick_size=0.5),
}

SYMBOLS = list(RENKO_EMA_PARAMS.keys())

# Warm-up start date
WARMUP = "2024-12-01"

# evaluation windows
PERIODS = {
    "Mar-2025":   ("2025-03-01", "2025-03-31"),
    "Apr-2025":   ("2025-04-01", "2025-04-30"),
    "May-2025":   ("2025-05-01", "2025-05-31"),
    "June-2025":  ("2025-06-01", "2025-06-30"),
    "July1-2025": ("2025-07-01", "2025-07-14"),
}

# Collect results
results = []

def run_period(symbol, label, start, end):
    params = RENKO_EMA_PARAMS[symbol]
    # Load full data
    df = load_candles(symbol, WARMUP, end)
    df.index = pd.to_datetime(df.index)

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
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

    cerebro.addstrategy(
        RenkoEMAStrategy,
        fast_period=params["fast_period"],
        slow_period=params["slow_period"],
        renko_brick_size=params["renko_brick_size"],
        printlog=False
    )

    strat = cerebro.run()[0]
    sharpe  = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd      = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr      = strat.analyzers.trades.get_analysis()
    won     = tr.get("won",  {}).get("total", 0)
    lost    = tr.get("lost", {}).get("total", 0)
    tot     = tr.get("total",{}).get("closed", 0)
    winrate = (won / tot * 100) if tot else 0.0

    print(f"\n--- {symbol} | {label} @ RenkoEMA({params['fast_period']}X{params['slow_period']}) ---")
    print(f"Sharpe Ratio : {sharpe:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {winrate:.1f}% ({won}W/{lost}L)")

    # Store results
    results.append({
        "symbol":       symbol,
        "period_label": label,
        "start":        start,
        "end":          end,
        "fast_period":  params["fast_period"],
        "slow_period":  params["slow_period"],
        "brick_size":   params["renko_brick_size"],
        "sharpe":       sharpe,
        "drawdown":     dd,
        "trades":       tot,
        "win_rate":     winrate,
    })

if __name__ == "__main__":
    for sym in SYMBOLS:
        for label, (start, end) in PERIODS.items():
            run_period(sym, label, start, end)

    # Save results to CSV
    pd.DataFrame(results).to_csv("renko_ema_results.csv", index=False)
    print("\nWrote renko_ema_results.csv")
