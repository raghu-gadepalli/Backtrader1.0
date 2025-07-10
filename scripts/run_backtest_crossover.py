#!/usr/bin/env python3

import os, sys
from datetime import datetime

# Force non-interactive Agg backend
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

import backtrader as bt

# Add project root to sys.path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles       import load_candles
from strategies.HmaTrendStrategy import HmaTrendStrategy

RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def run(symbol, start, end, fast, slow, atr_mult=0.0):
    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # Load warmup + test data
    df = load_candles(symbol, "2025-04-01", end)
    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=1
    )
    cerebro.adddata(data, name=symbol)

    # Inject strategy
    cerebro.addstrategy(
        HmaTrendStrategy,
        fast=fast,
        slow=slow,
        atr_mult=atr_mult,
        printlog=True
    )

    strat = cerebro.run()[0]

    # Metrics
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

    # Manual plot of the two HMAs
    dates     = [bt.num2date(x) for x in data.datetime.array]
    close_arr = data.close.array
    h1        = strat.hma_fast.array
    h2        = strat.hma_slow.array

    plt.figure(figsize=(12,6))
    plt.plot(dates, close_arr, label="Close")
    plt.plot(dates, h1,       label=f"HMA Fast ({fast})")
    plt.plot(dates, h2,       label=f"HMA Slow ({slow})")
    plt.xlim(datetime.fromisoformat(start), datetime.fromisoformat(end))
    plt.legend()
    out = os.path.join(RESULTS_DIR, f"{symbol}_f{fast}_s{slow}_atr{atr_mult}.png")
    plt.savefig(out)
    plt.close()
    print(f"Saved plot: {out}\n")


if __name__ == "__main__":
    run(
        symbol="ICICIBANK",
        start="2025-04-01",
        end="2025-07-06",
        fast=600,
        slow=760,
        atr_mult=0.0
    )
