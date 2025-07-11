#!/usr/bin/env python3
# scripts/optimize_hma_two_stage_multi.py

import os
import sys

# ─── PROJECT ROOT ON PATH ──────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles    import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

# ─── USER PARAMETERS ──────────────────────────────────────────────────────────
# STOCKS       = ["ICICIBANK", "INFY", "RELIANCE"]  # …add more tickers here…
STOCKS       = ["INFY"]  # …add more tickers here…
WARMUP_START = "2025-04-01"
END          = "2025-07-06"
ATR_MULT     = 0.0

METRIC       = "sharpe"     # or "expectancy"
# FAST_RANGE   = range(160, 1001, 80)   # e.g. 160,240,…,960
# MID1_RANGE   = range(160, 1601, 160)  # e.g. 160,320,…,1600

FAST_RANGE   = range(60, 961, 60)    #  60,120,180,…,960
MID1_RANGE   = range(120, 1921, 120) # 120,240,360,…,1920


TOP_N        = 5                      # drill only top-5 from Stage-1
MID2_MULTS   = [2, 3]                 # mid2 = fast × 2 or × 3
MID3_MULTS   = [4, 5]                 # mid3 = fast × 4 or × 5


def backtest(symbol, fast, mid1, mid2, mid3, atr_mult):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    df = load_candles(symbol, WARMUP_START, END)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data)
    cerebro.addstrategy(
        HmaStateStrengthStrategy,
        fast=fast, mid1=mid1, mid2=mid2, mid3=mid3,
        atr_mult=atr_mult, printlog=False
    )
    strat = cerebro.run()[0]

    # ── metric: Sharpe ratio ──────────────────────────────────────────────────
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio")
    sharpe = sharpe if sharpe is not None else float("-inf")

    # ── metric: Expectancy ─────────────────────────────────────────────────────
    tr = strat.analyzers.trades.get_analysis()
    won, lost = (tr.get("won",{}).get("total", 0),
                 tr.get("lost",{}).get("total", 0))
    avg_w = tr.get("won",{}).get("pnl",{}).get("average", 0.0)
    avg_l = tr.get("lost",{}).get("pnl",{}).get("average", 0.0)
    total = won + lost
    if total:
        wr = won / total
        lr = lost / total
        expectancy = wr * avg_w + lr * avg_l
    else:
        expectancy = float("-inf")

    return sharpe, expectancy, won, lost


if __name__ == "__main__":
    for SYMBOL in STOCKS:
        print(f"\n\n====== OPTIMIZING {SYMBOL} ======\n")

        # ── Stage-1: scan fast/mid1 ─────────────────────────────────────────────
        stage1 = []
        for fast in FAST_RANGE:
            for mid1 in MID1_RANGE:
                s, e, won, lost = backtest(SYMBOL, fast, mid1, fast*2, fast*4, ATR_MULT)
                stage1.append((fast, mid1, s, e))
                print(f"[{SYMBOL}] Stage1 fast={fast}, mid1={mid1} → "
                      f"Sharpe={s: .3f}, Exp={e: .3f}, W/L={won}/{lost}")

        # ── pick top N by METRIC ────────────────────────────────────────────────
        idx = 2 if METRIC == "sharpe" else 3
        top_pairs = sorted(stage1, key=lambda x: x[idx], reverse=True)[:TOP_N]

        print(f"\n[{SYMBOL}] === Top {TOP_N} by {METRIC} ===")
        for fast, mid1, s, e in top_pairs:
            print(f"  fast={fast}, mid1={mid1} → Sharpe={s: .3f}, Exp={e: .3f}")

        # ── Stage-2: drill only those top pairs through mid2/mid3 ───────────────
        print(f"\n[{SYMBOL}] === Stage-2 on mid2/mid3 ===")
        for fast, mid1, _, _ in top_pairs:
            for m2m in MID2_MULTS:
                for m3m in MID3_MULTS:
                    mid2 = fast * m2m
                    mid3 = fast * m3m
                    s2, e2, won2, lost2 = backtest(SYMBOL, fast, mid1, mid2, mid3, ATR_MULT)
                    print(f"  fast={fast}, mid1={mid1}, mid2={mid2}, mid3={mid3} → "
                          f"Sharpe={s2: .3f}, Exp={e2: .3f}, W/L={won2}/{lost2}")
