#!/usr/bin/env python3
# scripts/compare_hma_top3.py

import os
import sys

# ─── PROJECT ROOT ON PATH ──────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


import backtrader as bt
from data.load_candles import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

# ─── USER CONFIG ─────────────────────────────────────────────────────────────
SYMBOL     = "INFY"   # change to "ICICIBANK" or "RELIANCE" as needed
WARMUP     = "2025-04-01"
END        = "2025-07-06"
ATR_MULT   = 0.0

# ─── YOUR TOP-3 CANDIDATES FOR THIS SYMBOL ───────────────────────────────────
# pull these from your .csvs: first 3 you want to test
CANDIDATES = [
    # 60-grid #1
    {"label":"60-grid-1", "fast":160, "mid1":1600, "mid2":320,  "mid3":640,  "atr_mult":ATR_MULT},
    # 60-grid #2
    {"label":"60-grid-2", "fast":160, "mid1":160,  "mid2":320,  "mid3":640,  "atr_mult":ATR_MULT},
    # 80-grid #1
    {"label":"80-grid-1", "fast":700, "mid1":560,  "mid2":1400, "mid3":2800, "atr_mult":ATR_MULT},
]

# ─── BACKTEST FUNCTION ────────────────────────────────────────────────────────
def run_bt(symbol, cfg):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    df = load_candles(symbol, WARMUP, END)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes, compression=1)
    cerebro.adddata(data)
    cerebro.addstrategy(HmaStateStrengthStrategy,
                        fast=cfg["fast"], mid1=cfg["mid1"],
                        mid2=cfg["mid2"], mid3=cfg["mid3"],
                        atr_mult=cfg["atr_mult"], printlog=False)

    strat = cerebro.run()[0]

    # Sharpe
    s = strat.analyzers.sharpe.get_analysis().get("sharperatio") or float("-inf")
    # Win‐rate
    tr = strat.analyzers.trades.get_analysis()
    won  = tr.get("won",{}).get("total",0)
    lost = tr.get("lost",{}).get("total",0)
    total= won+lost
    wr = won/total if total else 0.0

    return s, wr, total

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\nResults for {SYMBOL}\n" + "-"*40)
    print(f"{'Label':<12} {'Sharpe':>7}   {'Win%':>6}   {'Trades':>6}")
    for cfg in CANDIDATES:
        s, wr, t = run_bt(SYMBOL, cfg)
        print(f"{cfg['label']:<12} {s:7.3f}   {wr:6.2%}   {t:6d}")
    print()
