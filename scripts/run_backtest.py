#!/usr/bin/env python3
# scripts/run_backtest.py

import os
import sys

# ─── FORCE AGG BACKEND ─────────────────────────────────────────────────────────
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt

import backtrader as bt

# ─── SETUP PROJECT PATH ─────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles            import load_candles
from strategies.HmaTrendStrategy  import HmaTrendStrategy

# ─── ENSURE RESULTS DIR ─────────────────────────────────────────────────────────
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def run(symbol: str,
        start:  str,
        end:    str,
        fast:   int,
        slow:   int):

    cerebro = bt.Cerebro()

    # ─── 1) Add performance analyzers ─────────────────────────────────────────
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # ─── 2) Load and feed data ───────────────────────────────────────────────────
    df = load_candles(symbol, start, end)
    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=1
    )
    cerebro.adddata(data, name=symbol)

    # ─── 3) Add the strategy ─────────────────────────────────────────────────────
    cerebro.addstrategy(
        HmaTrendStrategy,
        fast=fast,
        slow=slow,
        printlog=False
    )

    # ─── 4) Run backtest ─────────────────────────────────────────────────────────
    strat = cerebro.run()[0]

    # ─── 5) Extract analyzer results ────────────────────────────────────────────
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", None)
    dd     = strat.analyzers.drawdown.get_analysis()
    tr     = strat.analyzers.trades.get_analysis()

    won     = tr.won.total
    lost    = tr.lost.total
    total   = tr.total.closed
    winrate = (won / total * 100) if total else 0.0
    maxdd   = dd.max.drawdown

    print("\n=== Performance Metrics ===")
    print(f"Sharpe Ratio : {sharpe:.2f}" if sharpe is not None else "Sharpe Ratio : N/A")
    print(f"Max Drawdown : {maxdd:.2f}%")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winrate:.1f}% ({won}W/{lost}L)\n")

    # ─── 6) Manual plot of price + HMAs ──────────────────────────────────────────
    # Retrieve the single strategy instance
    strat = strat

    # Pull arrays from the first data feed
    data0     = strat.datas[0]
    dates     = [bt.num2date(x) for x in data0.datetime.array]
    close_arr = data0.close.array
    hma_f     = strat.hma_fast.array
    hma_s     = strat.hma_slow.array

    plt.figure(figsize=(12, 6))
    plt.plot(dates, close_arr, label="Close", linewidth=1)
    plt.plot(dates, hma_f,     label=f"HMA Fast ({fast})", linewidth=1)
    plt.plot(dates, hma_s,     label=f"HMA Slow ({slow})", linewidth=1)
    plt.title(f"{symbol}  Close vs HMA Fast/Slow")
    plt.xlabel("Time")
    plt.ylabel("Price")
    plt.legend()
    plt.tight_layout()

    out_path = os.path.join(
        RESULTS_DIR,
        f"{symbol}_metrics_hma_fast{fast}_slow{slow}.png"
    )
    plt.savefig(out_path)
    plt.close()
    print(f"Saved plot: {out_path}\n")


if __name__ == "__main__":
    run(
        symbol="INFY",
        start="2025-04-01",
        end="2025-07-06",
        fast=600,
        slow=2000
    )
