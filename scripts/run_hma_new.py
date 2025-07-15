#!/usr/bin/env python3
# scripts/run_hma_existing.py

import os, sys
from datetime import datetime

# force headless plotting
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

# --- ensure project root on path ---
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles                   import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# your best-found params per symbol
PARAMS = {
  "ICICIBANK": dict(fast= 240, mid1= 300, mid2=480, mid3=600, atr_mult=0.0),
  "INFY":      dict(fast=  80, mid1= 120, mid2= 120, mid3=120, atr_mult=0.0),
  "RELIANCE":  dict(fast=  520, mid1= 1680, mid2= 1680, mid3=1680, atr_mult=0.0),
}

WARMUP_START = "2025-04-01"
TRAIN_START  = "2025-05-01"
TRAIN_END    = "2025-05-31"
TEST_START   = "2025-06-01"
TEST_END     = "2025-06-30"

def run_period(symbol, period_start, period_end, **p):
    """Run Cerebro from WARMUP_START→period_end, then report metrics
       but zoom x-axis to period_start→period_end."""
    cerebro = bt.Cerebro()
    # analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # load full warmup+period data
    df = load_candles(symbol, WARMUP_START, period_end)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    # add existing strategy
    cerebro.addstrategy(HmaStateStrengthStrategy,
                        fast      = p["fast"],
                        mid1      = p["mid1"],
                        mid2      = p["mid2"],
                        mid3      = p["mid3"],
                        atr_mult  = p["atr_mult"],
                        printlog  = False)

    strat = cerebro.run()[0]

    # extract metrics
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd     = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr     = strat.analyzers.trades.get_analysis()
    won    = tr.get("won", {}).get("total", 0)
    lost   = tr.get("lost", {}).get("total", 0)
    total  = tr.get("total", {}).get("closed", 0)
    winr   = (won/total*100) if total else 0.0

    print(f"\n--- {symbol} | {period_start} → {period_end} ---")
    print(f"Sharpe Ratio : {sharpe:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winr:.1f}% ({won}W/{lost}L)")

if __name__ == "__main__":
    for sym, params in PARAMS.items():
        # training
        run_period(sym, TRAIN_START, TRAIN_END, **params)
        # testing
        run_period(sym, TEST_START,  TEST_END,  **params)
