#!/usr/bin/env python3
# scripts/run_reliance_infy_strength.py

import os, sys
from datetime import datetime

#  FORCE HEADLESS MPL BACKEND 
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

import backtrader as bt

#  PROJECT ROOT 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles                import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

#  OUTPUT DIRECTORY 
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def run_strength(symbol: str, start: str, end: str,
                 fast: int, mid1: int, mid2: int, mid3: int,
                 atr_mult: float = 0.0):
    """
    Backtest the 4-HMA state+strength strategy on `symbol`
    with (fast, mid1, mid2, mid3) and ATR gating.
    """
    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # load warm-up + test data
    WARMUP_START = "2025-04-01"
    df = load_candles(symbol, WARMUP_START, end)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    # attach strategy
    cerebro.addstrategy(
        HmaStateStrengthStrategy,
        fast=fast, mid1=mid1, mid2=mid2, mid3=mid3,
        atr_mult=atr_mult,
        printlog=True
    )

    strat = cerebro.run()[0]

    # grab metrics
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", None)
    dd     = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr     = strat.analyzers.trades.get_analysis()
    won    = tr.get("won",   {}).get("total", 0)
    lost   = tr.get("lost",  {}).get("total", 0)
    total  = tr.get("total", {}).get("closed", 0)
    winr   = (won/total*100) if total else 0.0

    print(f"\n=== {symbol}  fast={fast}, mid1={mid1}  mid2={mid2}, mid3={mid3}  ATR{atr_mult} ===")
    print(f"Sharpe Ratio : {sharpe:.2f}" if sharpe is not None else "Sharpe Ratio : N/A")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winr:.1f}% ({won}W/{lost}L)\n")

    # plot close + fast/mid1
    data0     = strat.datas[0]
    dates     = [bt.num2date(x) for x in data0.datetime.array]
    close_arr = data0.close.array
    hma_f     = strat.hma.array
    hma_m1    = strat.hma_mid1.array

    plt.figure(figsize=(12, 6))
    plt.plot(dates,     close_arr, label="Close", linewidth=1)
    plt.plot(dates,     hma_f,     label=f"HMA_FAST({fast})", linewidth=1)
    plt.plot(dates,     hma_m1,    label=f"HMA_MID1({mid1})",linewidth=1)
    plt.xlim(datetime.fromisoformat(start), datetime.fromisoformat(end))
    plt.title(f"{symbol}  fast={fast}, mid1={mid1}, ATR{atr_mult}")
    plt.xlabel("Time"); plt.ylabel("Price"); plt.legend(); plt.tight_layout()

    outfile = os.path.join(
        RESULTS_DIR,
        f"{symbol}_f{fast}_m1{mid1}_m2{mid2}_m3{mid3}_atr{atr_mult}.png"
    )
    plt.savefig(outfile)
    plt.close()
    print(f"Saved plot: {outfile}\n")


if __name__ == "__main__":
    TESTS = {
        "INFY":      dict(fast=200, mid1=300,  mid2=1200, mid3=3800, atr_mult=0.0),
        "RELIANCE":  dict(fast= 80, mid1=640,  mid2=1200, mid3=3800, atr_mult=0.0),
    }

    START = "2025-04-01"
    END   = "2025-07-06"

    for sym, params in TESTS.items():
        run_strength(sym, START, END, **params)
