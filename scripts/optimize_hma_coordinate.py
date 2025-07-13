#!/usr/bin/env python3
"""
scripts/optimize_hma_coordinate.py

Three-pass coordinate descent for multi-HMA:
  1) Sweep (fast, mid1)
  2) Drill mid2 on top heads
  3) Drill mid3 on top mid2 combos

Tie-breaker: primary metric (e.g. Sharpe), secondary expectancy, tertiary fewer trades.
Final top combos are written to CSV per symbol.
"""

import os
import sys
import csv

# ─── project root on path ─────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles                   import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

# ─── USER PARAMETERS ──────────────────────────────────────────────────────────
# STOCKS       = ["ICICIBANK", "INFY", "RELIANCE"]
STOCKS       = ["RELIANCE"]
WARMUP_START = "2025-04-01"
END          = "2025-07-06"
ATR_MULT     = 0.0

METRIC       = "sharpe"   # or "expectancy"

PASS1_N      = 4          # number of (fast,mid1) heads to carry to pass2
PASS2_N      = 4          # number of (fast,mid1,mid2) combos to carry to pass3
PASS3_N      = 4          # number of final (fast,mid1,mid2,mid3) combos to output

DISTINCT1    = True       # enforce distinct fasts in pass1
DISTINCT2    = True       # enforce distinct mid2s in pass2
DISTINCT3    = True       # enforce distinct mid3s in pass3

# FAST_RANGE   = range(30, 181, 30)    # 30,60,90,120,150,180
# MID1_RANGE   = range(120, 721, 120)  # 120,240,360,480,600,720
# MID2_RANGE   = [120, 180, 240, 360]  # explicit mids to try in pass2
# MID3_RANGE   = [240, 360, 480, 720]  # explicit mids to try in pass3

# FAST_RANGE   = range(60, 360, 60)    # 30,60,90,120,150,180
# MID1_RANGE   = range(120, 960, 60)  # 120,240,360,480,600,720
# MID2_RANGE   = [240, 360, 480, 600, 720, 840, 960, 1080, 1200]  # explicit mids to try in pass2
# MID3_RANGE   = [360, 480, 600, 720, 840, 960, 1080, 1200, 1440]  # explicit mids to try in pass3

FAST_RANGE   = range(180, 480, 60)    # 30,60,90,120,150,180
MID1_RANGE   = range(240, 960, 60)  # 120,240,360,480,600,720
MID2_RANGE   = [360, 480, 600, 720, 840, 960, 1080, 1200]  # explicit mids to try in pass2
MID3_RANGE   = [480, 600, 720, 840, 960, 1080, 1200, 1440]  # explicit mids to try in pass3
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

def sort_key(r):
    # primary: metric desc, secondary: expectancy desc, tertiary: trades asc
    return (-r[METRIC], -r["expectancy"], r["trades"])

def stage1(symbol):
    print(f"\n[{symbol}] PASS 1: sweeping (fast, mid1)")
    results = []
    total = sum(1 for f in FAST_RANGE for m1 in MID1_RANGE if f < m1)
    cnt = 0
    for fast in FAST_RANGE:
        for mid1 in MID1_RANGE:
            if fast >= mid1: continue
            cnt += 1
            s,e,won,lost = backtest(symbol, fast, mid1, fast*2, fast*4, ATR_MULT)
            trades = won + lost
            print(f"  [{cnt}/{total}] fast={fast}, mid1={mid1} → Sharpe={s:.3f}, Exp={e:.3f}, Trades={trades}")
            results.append({
                "fast": fast, "mid1": mid1,
                "sharpe": s, "expectancy": e,
                "trades": trades, "win_rate": (won/trades*100) if trades else 0
            })
    results.sort(key=sort_key)
    selected, seen = [], set()
    for r in results:
        if DISTINCT1 and r["fast"] in seen: continue
        selected.append(r); seen.add(r["fast"])
        if len(selected) >= PASS1_N: break
    print(f"\n[{symbol}] PASS 1 selected heads:")
    for r in selected:
        print(f"    fast={r['fast']}, mid1={r['mid1']} → {METRIC}={r[METRIC]:.3f}, Trades={r['trades']}")
    return selected

def stage2(symbol, heads1):
    print(f"\n[{symbol}] PASS 2: drilling mid2 on {len(heads1)} heads")
    results = []
    total = sum(1 for h in heads1 for m2 in MID2_RANGE if m2 > h["mid1"])
    cnt = 0
    for h in heads1:
        fast, mid1 = h["fast"], h["mid1"]
        for mid2 in MID2_RANGE:
            if mid2 <= mid1: continue
            cnt += 1
            s,e,won,lost = backtest(symbol, fast, mid1, mid2, fast*4, ATR_MULT)
            trades = won + lost
            print(f"  [{cnt}/{total}] fast={fast}, mid1={mid1}, mid2={mid2}"
                  f" → Sharpe={s:.3f}, Exp={e:.3f}, Trades={trades}")
            results.append({
                "fast": fast, "mid1": mid1, "mid2": mid2,
                "sharpe": s, "expectancy": e,
                "trades": trades, "win_rate": (won/trades*100) if trades else 0
            })
    results.sort(key=sort_key)
    selected, seen = [], set()
    for r in results:
        if DISTINCT2 and r["mid2"] in seen: continue
        selected.append(r); seen.add(r["mid2"])
        if len(selected) >= PASS2_N: break
    print(f"\n[{symbol}] PASS 2 selected combos:")
    for r in selected:
        print(f"    fast={r['fast']}, mid1={r['mid1']}, mid2={r['mid2']}"
              f" → {METRIC}={r[METRIC]:.3f}, Trades={r['trades']}")
    return selected

def stage3(symbol, heads2):
    print(f"\n[{symbol}] PASS 3: drilling mid3 on {len(heads2)} combos")
    results = []
    total = sum(1 for h in heads2 for m3 in MID3_RANGE if m3 > h["mid2"])
    cnt = 0
    for h in heads2:
        fast, mid1, mid2 = h["fast"], h["mid1"], h["mid2"]
        for mid3 in MID3_RANGE:
            if mid3 <= mid2: continue
            cnt += 1
            s,e,won,lost = backtest(symbol, fast, mid1, mid2, mid3, ATR_MULT)
            trades = won + lost
            print(f"  [{cnt}/{total}] fast={fast}, mid1={mid1}, mid2={mid2}, mid3={mid3}"
                  f" → Sharpe={s:.3f}, Exp={e:.3f}, Trades={trades}")
            results.append({
                "fast": fast, "mid1": mid1, "mid2": mid2, "mid3": mid3,
                "sharpe": s, "expectancy": e,
                "trades": trades, "win_rate": (won/trades*100) if trades else 0
            })
    results.sort(key=sort_key)
    selected, seen = [], set()
    for r in results:
        if DISTINCT3 and r["mid3"] in seen: continue
        selected.append(r); seen.add(r["mid3"])
        if len(selected) >= PASS3_N: break
    print(f"\n[{symbol}] PASS 3 selected final combos:")
    for r in selected:
        print(f"    fast={r['fast']}, mid1={r['mid1']}, mid2={r['mid2']}, mid3={r['mid3']}"
              f"  {METRIC}={r[METRIC]:.4f}, Trades={r['trades']}, Win={r['win_rate']:.1f}%")
    # write final to CSV
    out = f"{symbol}_coordinate_hma_opt.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fast","mid1","mid2","mid3", METRIC,"trades","win_rate"])
        for r in selected:
            w.writerow([r["fast"],r["mid1"],r["mid2"],r["mid3"],
                        f"{r[METRIC]:.6f}", r["trades"], f"{r['win_rate']:.1f}"])
    print(f"\n✔ Wrote final {len(selected)} combos to {out}\n")
    return selected

if __name__ == "__main__":
    for SYMBOL in STOCKS:
        print(f"\n###### OPTIMIZING {SYMBOL} ######")
        h1 = stage1(SYMBOL)
        h2 = stage2(SYMBOL, h1)
        stage3(SYMBOL, h2)
