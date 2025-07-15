#!/usr/bin/env python3
"""
scripts/optimize_hma_coordinate_single_one_sheet.py

Three-pass HMA coordinate descent for one symbol, logging 
every trial with progress prints and all passes + shortlist 
flags in one Excel sheet.
"""

import os, sys
import backtrader as bt
import pandas as pd

#  project root on path 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles         import load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy

#  USER PARAMETERS 
SYMBOL       = "INFY"       #  change to "RELIANCE" or "ICICIBANK"
WARMUP_START = "2025-04-01"
END          = "2025-07-06"
ATR_MULT     = 0.0

METRIC       = "sharpe"     # or "expectancy"

PASS1_N      = 3            # survivors to pass2
PASS2_N      = 3            # survivors to pass3
PASS3_N      = 3            # final combos

DISTINCT1    = True         # enforce distinct fast in pass1 shortlist
DISTINCT2    = True         # enforce distinct mid2 in pass2 shortlist

#  per-symbol HMA grids 
# FAST_RANGE   = range(80, 400, 80)
# MID1_RANGE   = [int(1.5*f) for f in FAST_RANGE]
# MID2_RANGE   = [3*f        for f in FAST_RANGE]
# MID3_RANGE   = [6*f        for f in FAST_RANGE]

FAST_RANGE = [200, 250, 300, 350, 400] 
MID1_RANGE = [int(1.5*f) for f in FAST_RANGE]
MID2_RANGE = [3*f for f in FAST_RANGE]
MID3_RANGE = [6*f for f in FAST_RANGE]
# 

def backtest(symbol, fast, mid1, mid2, mid3, atr_mult):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,  _name="trades")

    df = load_candles(symbol, WARMUP_START, END)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data)
    cerebro.addstrategy(HmaMultiTrendStrategy,
                        fast=fast, mid1=mid1, mid2=mid2, mid3=mid3,
                        atr_mult=atr_mult, printlog=False)

    strat = cerebro.run()[0]
    s    = strat.analyzers.sharpe.get_analysis().get("sharperatio") or float("-inf")
    tr   = strat.analyzers.trades.get_analysis()
    won  = tr.get("won",{}).get("total",0)
    lost = tr.get("lost",{}).get("total",0)
    avg_w = tr.get("won",{}).get("pnl",{}).get("average",0.0)
    avg_l = tr.get("lost",{}).get("pnl",{}).get("average",0.0)
    tot   = won + lost
    exp   = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("-inf")
    return s, exp, won, lost

def sort_key(r):
    return (-r[METRIC], -r["expectancy"], r["trades"])

def optimize_one(symbol):
    print(f"\n###### OPTIMIZING {symbol} ######")

    stage1, stage2, stage3 = [], [], []

    # PASS 1
    combos1 = [(f, m1) for f in FAST_RANGE for m1 in MID1_RANGE if f < m1]
    total1 = len(combos1)
    print(f"[{symbol}] PASS 1: {total1} fastmid1 combos")
    for i, (fast, mid1) in enumerate(combos1, 1):
        s,e,won,lost = backtest(symbol, fast, mid1, fast*2, fast*4, ATR_MULT)
        trades = won + lost
        print(f"  [{i}/{total1}] fast={fast}, mid1={mid1}  S={s:.3f}, E={e:.3f}, T={trades}")
        stage1.append({
            "stage":1, "fast":fast, "mid1":mid1, "mid2":None, "mid3":None,
            "sharpe":s, "expectancy":e, "trades":trades,
            "win_rate": won/trades*100 if trades else 0
        })

    # shortlist PASS1
    s1s = sorted(stage1, key=sort_key)
    heads1, seen = [], set()
    for r in s1s:
        if DISTINCT1 and r["fast"] in seen: continue
        heads1.append(r); seen.add(r["fast"])
        if len(heads1) >= PASS1_N: break
    print(f"[{symbol}] PASS 1 shortlisted {len(heads1)} heads: {[(h['fast'],h['mid1']) for h in heads1]}")

    # PASS 2
    combos2 = [(h["fast"], h["mid1"], mid2)
               for h in heads1 for mid2 in MID2_RANGE if mid2 > h["mid1"]]
    total2 = len(combos2)
    print(f"\n[{symbol}] PASS 2: {total2} combos (fast,mid1,mid2)")
    for i,(fast,mid1,mid2) in enumerate(combos2,1):
        s,e,won,lost = backtest(symbol, fast, mid1, mid2, fast*4, ATR_MULT)
        trades = won + lost
        print(f"  [{i}/{total2}] fast={fast}, mid1={mid1}, mid2={mid2}  S={s:.3f}, E={e:.3f}, T={trades}")
        stage2.append({
            "stage":2, "fast":fast, "mid1":mid1, "mid2":mid2, "mid3":None,
            "sharpe":s, "expectancy":e, "trades":trades,
            "win_rate": won/trades*100 if trades else 0
        })

    # shortlist PASS2
    s2s = sorted(stage2, key=sort_key)
    heads2, seen = [], set()
    for r in s2s:
        if DISTINCT2 and r["mid2"] in seen: continue
        heads2.append(r); seen.add(r["mid2"])
        if len(heads2) >= PASS2_N: break
    print(f"[{symbol}] PASS 2 shortlisted {len(heads2)} heads: {[(h['fast'],h['mid1'],h['mid2']) for h in heads2]}")

    # PASS 3
    combos3 = [(h["fast"],h["mid1"],h["mid2"],mid3)
               for h in heads2 for mid3 in MID3_RANGE if mid3 > h["mid2"]]
    total3 = len(combos3)
    print(f"\n[{symbol}] PASS 3: {total3} combos (fast,mid1,mid2,mid3)")
    for i,(fast,mid1,mid2,mid3) in enumerate(combos3,1):
        s,e,won,lost = backtest(symbol, fast, mid1, mid2, mid3, ATR_MULT)
        trades = won + lost
        print(f"  [{i}/{total3}] fast={fast}, mid1={mid1}, mid2={mid2}, mid3={mid3}"
              f"  S={s:.3f}, E={e:.3f}, T={trades}")
        stage3.append({
            "stage":3, "fast":fast, "mid1":mid1, "mid2":mid2, "mid3":mid3,
            "sharpe":s, "expectancy":e, "trades":trades,
            "win_rate": won/trades*100 if trades else 0
        })

    # shortlist PASS3  final
    final_heads = sorted(stage3, key=sort_key)[:PASS3_N]
    print(f"[{symbol}] FINAL top {PASS3_N}: {[(h['fast'],h['mid1'],h['mid2'],h['mid3']) for h in final_heads]}")

    # annotate flags
    for r in stage1: r["short1"] = (r in heads1)
    for r in stage2: r["short2"] = (r in heads2)
    for r in stage3: r["final"]  = (r in final_heads)

    # combine & export
    df = pd.DataFrame(stage1 + stage2 + stage3)
    out = f"{symbol}_hma_opt_all.xlsx"
    df.to_excel(out, index=False)
    print(f"\n Wrote all stages + shortlist flags to {out}")

if __name__ == "__main__":
    optimize_one(SYMBOL)
