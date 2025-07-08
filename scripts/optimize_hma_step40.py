#!/usr/bin/env python3
# scripts/optimize_hma_step40.py

import os
import sys

# ─── HEADLESS AGG BACKEND ───────────────────────────────────────────────────────
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt
import pandas     as pd

# ─── PROJECT ROOT ON PATH ──────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles           import load_candles
from strategies.HmaTrendStrategy import HmaTrendStrategy

# ─── USER CONFIGURATION ────────────────────────────────────────────────────────
SYMBOL      = "INFY"
START       = "2025-04-01"
END         = "2025-07-06"
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Generate all HMA window lengths divisible by 40
# fast_vals = list(range(200, 1001, 40))   # 200, 240, 280, …,  960, 1000
# slow_vals = list(range(240, 3001, 40))   # 240, 280, 320, …, 2960, 3000


fast_vals = list(range(360, 641, 40))   # [360, 400, 440, 480, 520, 560, 600]
slow_vals = [int(f * 3.0) for f in fast_vals]  # keep the 3× ratio

def optimize():
    # preload your candle data once
    df_feed = load_candles(SYMBOL, START, END)

    records = []
    total_runs = sum(1 for f in fast_vals for s in slow_vals if s > f)
    print(f"Running {total_runs} (fast,slow) combos with 40-step…\n")

    for fast in fast_vals:
        for slow in slow_vals:
            if slow <= fast:
                continue

            cerebro = bt.Cerebro()

            # attach analyzers
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                                timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
            cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

            # add data & strategy
            data = bt.feeds.PandasData(dataname=df_feed,
                                       timeframe=bt.TimeFrame.Minutes,
                                       compression=1)
            cerebro.adddata(data, name=SYMBOL)
            cerebro.addstrategy(
                HmaTrendStrategy,
                fast=fast,
                slow=slow,
                atr_mult=0.0,  # disable ATR gating for this test
                printlog=False
            )

            # run backtest
            strat = cerebro.run()[0]

            # extract metrics
            sa     = strat.analyzers
            sharpe = sa.sharpe.get_analysis().get("sharperatio", float("nan"))
            dd     = sa.drawdown.get_analysis().max.drawdown
            tr     = sa.trades.get_analysis()
            total  = tr.total.closed or 0
            won    = tr.won.total   or 0
            winpct = (won / total * 100) if total else 0.0

            records.append({
                "fast":   fast,
                "slow":   slow,
                "sharpe": round(sharpe, 4),
                "max_dd": round(dd,     4),
                "trades": total,
                "win%":   round(winpct, 1),
            })

            print(f"✓ tested f={fast:<4} s={slow:<4} → Sharpe {sharpe:.4f}, Win% {winpct:.1f}%")

    # build results table
    df_res = pd.DataFrame(records)
    df_res = df_res.sort_values("sharpe", ascending=False).reset_index(drop=True)

    # write to CSV
    out_csv = os.path.join(RESULTS_DIR, "hma_40step_results.csv")
    df_res.to_csv(out_csv, index=False)

    # display top 10
    print("\nTop 10 HMA combos (40-step) by Sharpe:\n")
    print(df_res.head(10).to_string(index=False))
    print(f"\nFull results written to {out_csv}")

if __name__ == "__main__":
    optimize()
