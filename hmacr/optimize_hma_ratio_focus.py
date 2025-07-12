#!/usr/bin/env python3
# scripts/optimize_hma_ratio_focus.py

import os, sys
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt
import pandas     as pd

# ─── Project setup ─────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles           import load_candles
from strategies.HmaTrendStrategy import HmaTrendStrategy

SYMBOL      = "INFY"
START       = "2025-04-01"
END         = "2025-07-06"
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# focused fast windows and ratios
fast_vals = [400, 420, 440, 460]
ratios    = [1.3, 1.4, 1.5, 1.6]

def optimize_focus():
    df_feed = load_candles(SYMBOL, START, END)
    records = []

    total = len(fast_vals) * len(ratios)
    print(f"🔍 Running focused sweep: {total} combos (fast × ratio)…\n")

    for fast in fast_vals:
        for ratio in ratios:
            slow = int(fast * ratio)
            cerebro = bt.Cerebro()

            # attach analyzers
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                                timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
            cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

            # feed data & add strategy
            data = bt.feeds.PandasData(dataname=df_feed,
                                       timeframe=bt.TimeFrame.Minutes,
                                       compression=1)
            cerebro.adddata(data, name=SYMBOL)
            cerebro.addstrategy(HmaTrendStrategy,
                                fast=fast, slow=slow, printlog=False)

            strat = cerebro.run()[0]

            # extract metrics
            sa     = strat.analyzers
            sharpe = sa.sharpe.get_analysis().get("sharperatio", float("nan"))
            dd     = sa.drawdown.get_analysis().max.drawdown
            tr     = sa.trades.get_analysis()
            total_trades = tr.total.closed or 0
            won    = tr.won.total or 0
            winpct = (won / total_trades * 100) if total_trades else 0.0

            records.append({
                "fast":   fast,
                "ratio":  ratio,
                "slow":   slow,
                "sharpe": round(sharpe, 4),
                "max_dd": round(dd,     4),
                "trades": total_trades,
                "win%":   round(winpct, 1),
            })

            print(f"✓ f={fast:<3} r={ratio:<4} s={slow:<4} → Sharpe {sharpe:.4f}, Win% {winpct:.1f}%")

    df_res = pd.DataFrame(records)
    df_res = df_res.sort_values(["sharpe","ratio","fast"], ascending=[False,True,True])
    out_csv = os.path.join(RESULTS_DIR, "hma_ratio_focus.csv")
    df_res.to_csv(out_csv, index=False)

    print("\n📊 Top 10 focused combos by Sharpe:\n")
    print(df_res.head(10).to_string(index=False))
    print(f"\nFull results saved to {out_csv}")

if __name__ == "__main__":
    optimize_focus()
