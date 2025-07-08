#!/usr/bin/env python3
# scripts/optimize_hma_step40.py

import os
import sys

# ─── FORCE HEADLESS AGG BACKEND ────────────────────────────────────────────────
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

# fast from 200 → 1000 step 40
fast_vals = list(range(80, 1001, 40))
# slow from 240 → 3000 step 40
slow_vals = list(range(120, 3001, 40))


def optimize():
    # 1) Load the OHLCV once (warm-up + test)
    df_feed = load_candles(SYMBOL, START, END)

    records = []
    total_runs = len(fast_vals) * len(slow_vals)
    print(f"🔍 Running {total_runs} combos (fast, slow) with 40-step…\n")

    # 2) Loop over each (fast, slow) pair
    for fast in fast_vals:
        for slow in slow_vals:
            cerebro = bt.Cerebro()

            # Attach analyzers
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                                timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
            cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

            # Add data feed
            data = bt.feeds.PandasData(
                dataname=df_feed,
                timeframe=bt.TimeFrame.Minutes,
                compression=1
            )
            cerebro.adddata(data, name=SYMBOL)

            # Add strategy with this fast/slow, disabling ATR gating
            cerebro.addstrategy(
                HmaTrendStrategy,
                fast=fast,
                slow=slow,
                atr_mult=0.0,     # disable ATR filter for pure length sweep
                printlog=False
            )

            # Run backtest
            strat = cerebro.run()[0]

            # Extract metrics safely
            sa         = strat.analyzers
            raw_sharpe = sa.sharpe.get_analysis().get("sharperatio", None)
            sharpe     = round(raw_sharpe, 4) if raw_sharpe is not None else float("nan")
            dd         = sa.drawdown.get_analysis().max.drawdown
            tr         = sa.trades.get_analysis()

            total_trades = tr.get("total", {}).get("closed", 0)
            won          = tr.get("won",   {}).get("total",  0)
            winpct       = (won / total_trades * 100) if total_trades else 0.0

            records.append({
                "fast":   fast,
                "slow":   slow,
                "sharpe": sharpe,
                "max_dd": round(dd,          4),
                "trades": total_trades,
                "win%":   round(winpct,      1),
            })

            sharpe_str = f"{sharpe:.4f}" if raw_sharpe is not None else "N/A"
            print(f"✓ f={fast:<4} s={slow:<4} → Sharpe {sharpe_str}, Win% {winpct:.1f}%")

    # 3) Build & save results DataFrame
    df_res = pd.DataFrame(records)
    df_res = df_res.sort_values(["sharpe", "fast", "slow"], ascending=[False, True, True])
    out_csv = os.path.join(RESULTS_DIR, "hma_step40_results.csv")
    df_res.to_csv(out_csv, index=False)

    # 4) Display top 10
    print("\n📊 Top 10 HMA (fast, slow) by Sharpe:\n")
    print(df_res.head(10).to_string(index=False))
    print(f"\nFull results written to {out_csv}")


if __name__ == "__main__":
    optimize()
