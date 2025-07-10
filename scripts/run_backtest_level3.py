#!/usr/bin/env python3
import os, sys
from datetime import datetime

# ─── Force Agg backend (headless) ─────────────────────────────────────────────
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

import backtrader as bt

# ─── Project root on path ─────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles             import load_candles
from strategies.HmaLevel3Strategy  import HmaLevel3Strategy

# ─── Ensure results dir ───────────────────────────────────────────────────────
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def run(symbol: str, start: str, end: str, fast: int, mid1: int, atr_mult: float = 0.0):
    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # load warm-up + test data
    df = load_candles(symbol, "2025-04-01", end)
    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=1
    )
    cerebro.adddata(data, name=symbol)

    # inject our level-3 HMA strategy
    cerebro.addstrategy(
        HmaLevel3Strategy,
        fast=fast,
        mid1=mid1,
        atr_mult=atr_mult,
        printlog=True
    )

    strat = cerebro.run()[0]

    # extract metrics
    sa     = strat.analyzers
    sharpe = sa.sharpe.get_analysis().get("sharperatio", None)
    dd     = sa.drawdown.get_analysis().max.drawdown
    tr     = sa.trades.get_analysis()
    won    = tr.get("won",   {}).get("total", 0)
    lost   = tr.get("lost",  {}).get("total", 0)
    total  = tr.get("total", {}).get("closed",0)
    winr   = (won / total * 100) if total else 0.0

    print("\n=== Performance Metrics ===")
    print(f"Sharpe Ratio : {sharpe:.2f}" if sharpe is not None else "Sharpe Ratio : N/A")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winr:.1f}% ({won}W/{lost}L)\n")

    # plot close + HMAs
    dates     = [bt.num2date(x) for x in data.datetime.array]
    close_a   = data.close.array
    fast_a    = strat.hma_fast.array
    mid1_a    = strat.hma_mid1.array

    plt.figure(figsize=(12,6))
    plt.plot(dates, close_a, label="Close")
    plt.plot(dates, fast_a,  label=f"HMA Fast ({fast})")
    plt.plot(dates, mid1_a,  label=f"HMA Level-3 ({mid1})")
    plt.xlim(datetime.fromisoformat(start), datetime.fromisoformat(end))
    plt.legend()
    outfile = os.path.join(
        RESULTS_DIR,
        f"{symbol}_lvl3_f{fast}_m{mid1}_atr{atr_mult}.png"
    )
    plt.savefig(outfile)
    plt.close()
    print(f"Saved plot: {outfile}\n")


if __name__ == "__main__":
    run(
        symbol="INFY",
        start="2025-04-01",
        end="2025-07-06",
        fast=200,
        mid1=1200,
        atr_mult=0.0
    )
