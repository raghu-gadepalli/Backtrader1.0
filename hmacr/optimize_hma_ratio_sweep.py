#!/usr/bin/env python3
# scripts/optimize_hma_ratio_sweep.py

import os
import sys

#  FORCE HEADLESS AGG BACKEND 
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt
import pandas     as pd

#  PROJECT ROOT ON PATH 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles           import load_candles
from strategies.HmaTrendStrategy import HmaTrendStrategy

#  USER CONFIGURATION 
SYMBOL      = "INFY"
START       = "2025-04-01"
END         = "2025-07-06"
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# list of fast HMA windows to test
fast_vals = [80, 120, 160, 200, 240, 280, 320, 480, 640, 800]
# list of ratios to apply (slow = fast * ratio)
ratios    = [1.5, 2.0, 2.5, 3.0, 3.3, 3.5, 4.0]


def optimize():
    # 1) Load the OHLCV once
    df_feed = load_candles(SYMBOL, START, END)

    records = []
    total_runs = len(fast_vals) * len(ratios)
    print(f" Running {total_runs} combos (fast  ratio)\n")

    # 2) Loop over each ratio & fast combination
    for ratio in ratios:
        for fast in fast_vals:
            slow = int(fast * ratio)

            cerebro = bt.Cerebro()
            # Attach analyzers
            cerebro.addanalyzer(
                bt.analyzers.SharpeRatio, _name="sharpe",
                timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0
            )
            cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

            # Add data feed
            data = bt.feeds.PandasData(
                dataname=df_feed,
                timeframe=bt.TimeFrame.Minutes,
                compression=1
            )
            cerebro.adddata(data, name=SYMBOL)

            # Add strategy with this fast/slow
            cerebro.addstrategy(
                HmaTrendStrategy,
                fast=fast,
                slow=slow,
                atr_mult=0.0,    # disable ATR gating
                printlog=False
            )

            # Run
            strat = cerebro.run()[0]

            # Extract metrics
            sa         = strat.analyzers
            raw_sharpe = sa.sharpe.get_analysis().get("sharperatio", None)
            sharpe     = round(raw_sharpe, 4) if raw_sharpe is not None else float("nan")
            dd         = sa.drawdown.get_analysis().max.drawdown
            tr         = sa.trades.get_analysis()

            total_trades = tr.get("total", {}).get("closed", 0)
            won          = tr.get("won",   {}).get("total",  0)
            winpct       = (won / total_trades * 100) if total_trades else 0.0

            records.append({
                "ratio":  ratio,
                "fast":   fast,
                "slow":   slow,
                "sharpe": sharpe,
                "max_dd": round(dd,     4),
                "trades": total_trades,
                "win%":   round(winpct, 1),
            })

            sharpe_str = f"{sharpe:.4f}" if raw_sharpe is not None else "N/A"
            print(f" r={ratio:<3} f={fast:<4} s={slow:<4}  Sharpe {sharpe_str}, Win% {winpct:.1f}%")

    # 3) Build & save results DataFrame
    df_res = pd.DataFrame(records)
    df_res = df_res.sort_values(["sharpe", "ratio"], ascending=[False, True])
    out_csv = os.path.join(RESULTS_DIR, "hma_ratio_optimization.csv")
    df_res.to_csv(out_csv, index=False)

    # 4) Display top 10
    print("\n Top 10 HMA (ratio, fast, slow) by Sharpe:\n")
    print(df_res.head(10).to_string(index=False))
    print(f"\nFull results written to {out_csv}")


if __name__ == "__main__":
    optimize()
