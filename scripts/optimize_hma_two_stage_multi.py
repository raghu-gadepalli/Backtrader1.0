#!/usr/bin/env python3
"""
scripts/optimize_hma_coordinate.py

Three-pass coordinate descent for multi‐HMA:
  1) Sweep (fast, mid1)
  2) Drill mid2 for top heads
  3) Drill mid3 for top mid2 combos

All parameters are hard-coded below for easy editing.
"""

import os
import sys

# ─── project root on path ─────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles                   import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

# ─── USER PARAMETERS ──────────────────────────────────────────────────────────
# STOCKS       = ["ICICIBANK", "INFY", "RELIANCE"]
STOCKS       = ["INFY"]
WARMUP_START = "2025-04-01"
END          = "2025-07-06"
ATR_MULT     = 0.0

METRIC       = "sharpe"   # or "expectancy"

# How many to keep at each pass
PASS1_N      = 3          # number of (fast,mid1) heads
PASS2_N      = 3          # number of (fast,mid1,mid2) combos
PASS3_N      = 3          # number of final (fast,mid1,mid2,mid3) combos

# Enforce distinct on each pass?
DISTINCT1    = True       # distinct fasts in pass1
DISTINCT2    = True       # distinct mid2s in pass2
DISTINCT3    = True       # distinct mid3s in pass3

# Grids for each pass
FAST_RANGE   = range(30, 181, 30)    # 30,60,90,120,150,180
MID1_RANGE   = range(120, 721, 120)  # 120,240,360,480,600,720
MID2_RANGE   = [120, 180, 240, 360]  # explicit mids to try in pass2
MID3_RANGE   = [240, 360, 480, 720]  # explicit mids to try in pass3
# ──────────────────────────────────────────────────────────────────────────────

def backtest(symbol, fast, mid1, mid2, mid3, atr_mult):
    """Run Backtrader for given HMA params, return sharpe, expectancy, wins, losses."""
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,  _name="trades")

    df = load_candles(symbol, WARMUP_START, END)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data)
    cerebro.addstrategy(HmaStateStrengthStrategy,
                        fast=fast, mid1=mid1, mid2=mid2, mid3=mid3,
                        atr_mult=atr_mult, printlog=False)

    strat = cerebro.run()[0]
    s = strat.analyzers.sharpe.get_analysis().get("sharperatio") or float("-inf")
    tr = strat.analyzers.trades.get_analysis()
    won  = tr.get("won",{}).get("total",0)
    lost = tr.get("lost",{}).get("total",0)
    avg_w = tr.get("won",{}).get("pnl",{}).get("average",0.0)
    avg_l = tr.get("lost",{}).get("pnl",{}).get("average",0.0)
    tot   = won + lost
    exp   = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("-inf")

    return s, exp, won, lost

def stage1(symbol):
    """Pass 1: sweep (fast, mid1)."""
    print(f"\n[{symbol}] PASS 1: sweeping fast & mid1")
    results = []
    total = sum(1 for f in FAST_RANGE for m1 in MID1_RANGE if f < m1)
    count = 0
    for fast in FAST_RANGE:
        for mid1 in MID1_RANGE:
            if fast >= mid1:
                continue
            count += 1
            s,e,won,lost = backtest(symbol, fast, mid1, fast*2, fast*4, ATR_MULT)
            print(f"  [{count}/{total}] fast={fast}, mid1={mid1} → Sharpe={s:.3f}, Exp={e:.3f}")
            results.append({
                "fast": fast, "mid1": mid1,
                "sharpe": s,  "expectancy": e,
                "trades": won+lost, "win_rate": (won/(won+lost)*100) if (won+lost) else 0
            })
    # sort and select top
    results.sort(key=lambda r: r[METRIC], reverse=True)
    selected = []
    seen_f = set()
    for r in results:
        f = r["fast"]
        if DISTINCT1 and f in seen_f:
            continue
        selected.append(r)
        seen_f.add(f)
        if len(selected) >= PASS1_N:
            break
    print(f"\n[{symbol}] PASS 1 selected {len(selected)} heads:")
    for r in selected:
        print(f"    fast={r['fast']}, mid1={r['mid1']} → {METRIC}={r[METRIC]:.3f}, trades={r['trades']}")
    return selected

def stage2(symbol, heads1):
    """Pass 2: sweep mid2 for each head from pass1."""
    print(f"\n[{symbol}] PASS 2: sweeping mid2 for {len(heads1)} heads")
    results = []
    total = sum(len(MID2_RANGE) for _ in heads1)
    count = 0
    for h in heads1:
        fast, mid1 = h["fast"], h["mid1"]
        for mid2 in MID2_RANGE:
            if mid2 <= mid1:
                continue
            count += 1
            s,e,won,lost = backtest(symbol, fast, mid1, mid2, fast*4, ATR_MULT)
            print(f"  [{count}/{total}] fast={fast}, mid1={mid1}, mid2={mid2} → Sharpe={s:.3f}, Exp={e:.3f}")
            results.append({
                "fast": fast, "mid1": mid1, "mid2": mid2,
                "sharpe": s, "expectancy": e,
                "trades": won+lost, "win_rate": (won/(won+lost)*100) if (won+lost) else 0
            })
    results.sort(key=lambda r: r[METRIC], reverse=True)
    selected = []
    seen_m2 = set()
    for r in results:
        m2 = r["mid2"]
        if DISTINCT2 and m2 in seen_m2:
            continue
        selected.append(r)
        seen_m2.add(m2)
        if len(selected) >= PASS2_N:
            break
    print(f"\n[{symbol}] PASS 2 selected {len(selected)} combos:")
    for r in selected:
        print(f"    fast={r['fast']}, mid1={r['mid1']}, mid2={r['mid2']} → {METRIC}={r[METRIC]:.3f}")
    return selected

def stage3(symbol, heads2):
    """Pass 3: sweep mid3 for each combo from pass2."""
    print(f"\n[{symbol}] PASS 3: sweeping mid3 for {len(heads2)} combos")
    results = []
    total = sum(len(MID3_RANGE) for _ in heads2)
    count = 0
    for h in heads2:
        fast, mid1, mid2 = h["fast"], h["mid1"], h["mid2"]
        for mid3 in MID3_RANGE:
            if mid3 <= mid2:
                continue
            count += 1
            s,e,won,lost = backtest(symbol, fast, mid1, mid2, mid3, ATR_MULT)
            print(f"  [{count}/{total}] fast={fast}, mid1={mid1}, mid2={mid2}, mid3={mid3} → Sharpe={s:.3f}, Exp={e:.3f}")
            results.append({
                "fast": fast, "mid1": mid1, "mid2": mid2, "mid3": mid3,
                "sharpe": s, "expectancy": e,
                "trades": won+lost, "win_rate": (won/(won+lost)*100) if (won+lost) else 0
            })
    results.sort(key=lambda r: r[METRIC], reverse=True)
    selected = []
    seen_m3 = set()
    for r in results:
        m3 = r["mid3"]
        if DISTINCT3 and m3 in seen_m3:
            continue
        selected.append(r)
        seen_m3.add(m3)
        if len(selected) >= PASS3_N:
            break
    print(f"\n[{symbol}] PASS 3 selected {len(selected)} final combos:")
    for r in selected:
        print(f"    fast={r['fast']}, mid1={r['mid1']}, mid2={r['mid2']}, mid3={r['mid3']}  "
              f"{METRIC}={r[METRIC]:.4f}, trades={r['trades']}, win={r['win_rate']:.1f}%")
    return selected

if __name__ == "__main__":
    for SYMBOL in STOCKS:
        print(f"\n########## {SYMBOL} OPTIMIZATION ##########")
        heads1 = stage1(SYMBOL)
        heads2 = stage2(SYMBOL, heads1)
        final = stage3(SYMBOL, heads2)
        print(f"\n*** {SYMBOL} FINAL TOP {PASS3_N} COMBOS ***\n")
