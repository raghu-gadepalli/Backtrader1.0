#!/usr/bin/env python3
"""
scripts/optimize_hma_coordinate.py

Three-pass coordinate descent for multi-HMA, logging **all** stage results:
  stage 1 → fast, mid1
  stage 2 → + mid2
  stage 3 → + mid3

Outputs one CSV per symbol with a “stage” column, then prints & writes the final top combos.
"""

import os
import sys
import csv

# ─── project root on path ─────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles         import load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy

# ─── USER PARAMETERS ──────────────────────────────────────────────────────────
STOCKS       = ["ICICIBANK", "INFY", "RELIANCE"]
WARMUP_START = "2025-04-01"
END          = "2025-07-06"
ATR_MULT     = 0.0

METRIC       = "sharpe"   # or "expectancy"

PASS1_N      = 3          # survivors to pass2
PASS2_N      = 3          # survivors to pass3
PASS3_N      = 3          # final combos to output

DISTINCT1    = True       # distinct fast in pass1
DISTINCT2    = True       # distinct mid2 in pass2
DISTINCT3    = True       # distinct mid3 in pass3

# Per-symbol grids
FAST_RANGES = {
    "ICICIBANK": range(30, 181, 30),
    "INFY":      range(30, 181, 30),
    "RELIANCE":  range(60, 361, 60),
}
MID1_RANGES = {
    "ICICIBANK": range(120, 721, 120),
    "INFY":      range(120, 721, 120),
    "RELIANCE":  range(480, 1681, 240),
}
MID2_RANGES = {
    "ICICIBANK": [120, 180, 240, 360, 840],
    "INFY":      [120, 180, 240, 360],
    "RELIANCE":  [840, 960, 1200, 1440],
}
MID3_RANGES = {
    "ICICIBANK": [240, 360, 480, 720],
    "INFY":      [240, 360, 480, 720],
    "RELIANCE":  [1680, 2160, 2880],
}
# ──────────────────────────────────────────────────────────────────────────────

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
                        fast=fast, mid1=mid1,
                        mid2=mid2, mid3=mid3,
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
    # primary: metric desc, secondary: expectancy desc, tertiary: trades asc
    return (-r[METRIC], -r["expectancy"], r["trades"])

def optimize_symbol(symbol):
    # open CSV for **all** stage logs
    out_all = f"{symbol}_hma_opt_all_stages.csv"
    f_all = open(out_all, "w", newline="")
    writer = csv.writer(f_all)
    writer.writerow([
        "stage","fast","mid1","mid2","mid3","sharpe",
        "expectancy","trades","win_rate"
    ])

    # --- PASS 1: fast & mid1 ------------------------------------------------
    print(f"\n[{symbol}] PASS 1: sweeping fast & mid1")
    s1_results = []
    FAST_RANGE = FAST_RANGES[symbol]
    MID1_RANGE = MID1_RANGES[symbol]
    total = sum(1 for f in FAST_RANGE for m1 in MID1_RANGE if f < m1)
    cnt = 0
    for fast in FAST_RANGE:
        for mid1 in MID1_RANGE:
            if fast >= mid1: continue
            cnt += 1
            s,e,won,lost = backtest(symbol, fast, mid1, fast*2, fast*4, ATR_MULT)
            trades = won+lost; wr = (won/trades*100) if trades else 0
            print(f"  [{cnt}/{total}] fast={fast}, mid1={mid1} → Sharpe={s:.3f}, Exp={e:.3f}, Trades={trades}")
            rec = dict(stage=1, fast=fast, mid1=mid1, mid2="", mid3="",
                       sharpe=s, expectancy=e, trades=trades, win_rate=wr)
            writer.writerow(rec.values())
            s1_results.append(rec)

    # pick pass1 survivors
    s1_results.sort(key=sort_key)
    heads1, seen = [], set()
    for r in s1_results:
        if DISTINCT1 and r["fast"] in seen: continue
        heads1.append(r); seen.add(r["fast"])
        if len(heads1)>=PASS1_N: break

    # --- PASS 2: add mid2 ----------------------------------------------------
    print(f"\n[{symbol}] PASS 2: drilling mid2 on {len(heads1)} heads")
    s2_results = []
    MID2_RANGE = MID2_RANGES[symbol]
    total = sum(1 for h in heads1 for m2 in MID2_RANGE if m2 > h["mid1"])
    cnt = 0
    for h in heads1:
        fast, mid1 = h["fast"], h["mid1"]
        for mid2 in MID2_RANGE:
            if mid2 <= mid1: continue
            cnt += 1
            s,e,won,lost = backtest(symbol, fast, mid1, mid2, fast*4, ATR_MULT)
            trades = won+lost; wr = (won/trades*100) if trades else 0
            print(f"  [{cnt}/{total}] fast={fast}, mid1={mid1}, mid2={mid2} → Sharpe={s:.3f}, Exp={e:.3f}, Trades={trades}")
            rec = dict(stage=2, fast=fast, mid1=mid1, mid2=mid2, mid3="",
                       sharpe=s, expectancy=e, trades=trades, win_rate=wr)
            writer.writerow(rec.values())
            s2_results.append(rec)

    # pick pass2 survivors
    s2_results.sort(key=sort_key)
    heads2, seen = [], set()
    for r in s2_results:
        if DISTINCT2 and r["mid2"] in seen: continue
        heads2.append(r); seen.add(r["mid2"])
        if len(heads2)>=PASS2_N: break

    # --- PASS 3: add mid3 ----------------------------------------------------
    print(f"\n[{symbol}] PASS 3: drilling mid3 on {len(heads2)} combos")
    s3_results = []
    MID3_RANGE = MID3_RANGES[symbol]
    total = sum(1 for h in heads2 for m3 in MID3_RANGE if m3 > h["mid2"])
    cnt = 0
    for h in heads2:
        fast, mid1, mid2 = h["fast"], h["mid1"], h["mid2"]
        for mid3 in MID3_RANGE:
            if mid3 <= mid2: continue
            cnt += 1
            s,e,won,lost = backtest(symbol, fast, mid1, mid2, mid3, ATR_MULT)
            trades = won+lost; wr = (won/trades*100) if trades else 0
            print(f"  [{cnt}/{total}] fast={fast}, mid1={mid1}, mid2={mid2}, mid3={mid3} → Sharpe={s:.3f}, Exp={e:.3f}, Trades={trades}")
            rec = dict(stage=3, fast=fast, mid1=mid1, mid2=mid2, mid3=mid3,
                       sharpe=s, expectancy=e, trades=trades, win_rate=wr)
            writer.writerow(rec.values())
            s3_results.append(rec)

    f_all.close()
    print(f"\n✔ Wrote all stage-1/2/3 rows to {out_all}")

    # pick final survivors and write separate CSV
    s3_results.sort(key=sort_key)
    final = s3_results[:PASS3_N]
    out_final = f"{symbol}_hma_opt_final.csv"
    with open(out_final, "w", newline="") as f2:
        w = csv.writer(f2)
        w.writerow(["fast","mid1","mid2","mid3",METRIC,"expectancy","trades","win_rate"])
        for r in final:
            w.writerow([r["fast"],r["mid1"],r["mid2"],r["mid3"],
                        f"{r[METRIC]:.6f}", f"{r['expectancy']:.6f}",
                        r["trades"], f"{r['win_rate']:.1f}%"])
    print(f"✔ Wrote top {PASS3_N} combos to {out_final}\n")

if __name__ == "__main__":
    for sym in STOCKS:
        print(f"\n====== OPTIMIZING {sym} ======")
        optimize_symbol(sym)
