#!/usr/bin/env python3
# scripts/optimize_icici_hma.py

import os, sys
from datetime import datetime

# ─── PROJECT ROOT ON PATH ──────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


import backtrader as bt
from data.load_candles import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy
from config.enums import TrendType

# ─── PROJECT ROOT ON PATH ──────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# --------------------------------------------------------------------
# PARAMETERS
SYMBOL    = "RELIANCE"
WARMUP    = "2025-04-01"
TRAIN_START = "2025-05-01"
TRAIN_END   = "2025-06-30"
RESULTS   = []

# fixed mids and ATR
MID2      = 1040
MID3      = 1520
ATR_MULT  = 0.0

# grid for fast / mid1
FAST_LIST = [400, 500, 600, 700, 800]
MID1_OFFS = [160, 240, 320]

# --------------------------------------------------------------------
def run_bt(fast, mid1):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", timeframe=bt.TimeFrame.Minutes)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    # load data (warmup+train)
    df = load_candles(SYMBOL, WARMUP, TRAIN_END)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes, compression=1)
    cerebro.adddata(data)

    # add strategy
    cerebro.addstrategy(
        HmaStateStrengthStrategy,
        fast=fast, mid1=mid1, mid2=MID2, mid3=MID3,
        atr_mult=ATR_MULT, printlog=False
    )

    strat = cerebro.run()[0]
    sr    = strat.analyzers.sharpe.get_analysis().get("sharperatio") or 0.0
    dd    = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr    = strat.analyzers.trades.get_analysis()
    wins  = tr.get("won",{}).get("total",0)
    losses= tr.get("lost",{}).get("total",0)
    total = tr.get("total",{}).get("closed",0)
    winr  = wins/total*100 if total else 0.0

    return dict(fast=fast, mid1=mid1, sharpe=sr, dd=dd, trades=total, winrate=winr)

# --------------------------------------------------------------------
if __name__ == "__main__":
    for fast in FAST_LIST:
        for off in MID1_OFFS:
            mid1 = fast + off
            res = run_bt(fast, mid1)
            RESULTS.append(res)
            print(f"Tested fast={fast}, mid1={mid1} → Sharpe={res['sharpe']:.3f}, Trades={res['trades']}, Win%={res['winrate']:.1f}")

    # sort & show top 5 by Sharpe
    top5 = sorted(RESULTS, key=lambda x: x["sharpe"], reverse=True)[:5]
    print("\n=== Top 5 RELIANCE fast/mid1 pairs ===")
    for r in top5:
        print(f"fast={r['fast']:>3}, mid1={r['mid1']:>4} — Sharpe {r['sharpe']:.3f}, DD {r['dd']:.2f}%, {r['winrate']:.1f}% win")
