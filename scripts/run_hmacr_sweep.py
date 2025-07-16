#!/usr/bin/env python3
# scripts/run_hmamulti_sweep.py

import os
import sys
import csv

# ─── project root ───────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles import load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy

# ─── user parameters ────────────────────────────────────────────────────────────

# list of symbols to test
SYMBOLS = ["ICICIBANK", "INFY", "RELIANCE"]

# common HMA parameter grids
FAST_RANGE  = range(30, 181, 30)
MID1_RANGE  = range(120, 721, 120)
MID2_LIST   = [120, 180, 240, 360, 840]
MID3_LIST   = [240, 360, 480, 720]

ATR_MULT = 0.0
METRIC   = "sharpe"   # or "expectancy"
PASS1_N  = 3
PASS2_N  = 3
PASS3_N  = 3
DISTINCT1 = True
DISTINCT2 = True

# ─── walk‑forward windows ───────────────────────────────────────────────────────
WINDOWS = [
    { "label": "Jan-Jun", "warm": "2024-12-01", "start": "2025-01-01", "end": "2025-06-30" },
    { "label": "Jan-Feb", "warm": "2025-01-01", "start": "2025-02-01", "end": "2025-02-28" },
    { "label": "Feb-Mar", "warm": "2025-02-01", "start": "2025-03-01", "end": "2025-03-31" },
    { "label": "Mar-Apr", "warm": "2025-03-01", "start": "2025-04-01", "end": "2025-04-30" },
]

# ─── backtest utility ───────────────────────────────────────────────────────────
def backtest(symbol, fast, mid1, mid2, mid3, atr_mult, warm, start, end):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    df = load_candles(symbol, warm, end)
    df.index = pd.to_datetime(df.index)

    data = bt.feeds.PandasData(
        dataname    = df,
        fromdate    = pd.to_datetime(start),
        todate      = pd.to_datetime(end),
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1,
    )
    cerebro.adddata(data)
    cerebro.addstrategy(
        HmaMultiTrendStrategy,
        fast=fast, mid1=mid1, mid2=mid2, mid3=mid3,
        atr_mult=atr_mult, printlog=False
    )

    strat = cerebro.run()[0]
    s = strat.analyzers.sharpe.get_analysis().get("sharperatio", float("-inf"))
    tr = strat.analyzers.trades.get_analysis()
    won  = tr.get("won", {}).get("total", 0)
    lost = tr.get("lost", {}).get("total", 0)
    trades = won + lost
    wr     = (won / trades * 100) if trades else 0.0

    avg_w = tr.get("won", {}).get("pnl", {}).get("average", 0.0)
    avg_l = tr.get("lost", {}).get("pnl", {}).get("average", 0.0)
    exp   = (won/trades)*avg_w + (lost/trades)*avg_l if trades else float("-inf")

    return {
        "sharpe":       s,
        "expectancy":   exp,
        "trades":       trades,
        "win_rate":     wr,
    }

# ─── per‑symbol, per‑window optimisation ─────────────────────────────────────────
def optimize_for_window(symbol, window):
    out_all   = f"{symbol}_hma_opt_all_{window['label']}.csv"
    out_final = f"{symbol}_hma_opt_final_{window['label']}.csv"

    # open CSV for all stage results
    with open(out_all, "w", newline="") as f_all:
        writer_all = csv.writer(f_all)
        writer_all.writerow(["stage","fast","mid1","mid2","mid3",
                             "sharpe","expectancy","trades","win_rate"])

        # PASS 1: fast & mid1 grid
        s1 = []
        for fast in FAST_RANGE:
            for mid1 in MID1_RANGE:
                if fast >= mid1: continue
                rec = backtest(symbol, fast, mid1, fast*2, fast*4,
                               ATR_MULT, window["warm"], window["start"], window["end"])
                row = dict(stage=1, fast=fast, mid1=mid1, mid2="", mid3="", **rec)
                writer_all.writerow(row.values())
                s1.append(row)
        s1.sort(key=lambda r: (-r[METRIC], -r["expectancy"], r["trades"]))
        heads1, seen = [], set()
        for r in s1:
            if DISTINCT1 and r["fast"] in seen: continue
            heads1.append(r); seen.add(r["fast"])
            if len(heads1) >= PASS1_N: break

        # PASS 2: add mid2
        s2 = []
        for h in heads1:
            for mid2 in MID2_LIST:
                if mid2 <= h["mid1"]: continue
                rec = backtest(symbol, h["fast"], h["mid1"], mid2, h["fast"]*4,
                               ATR_MULT, window["warm"], window["start"], window["end"])
                row = dict(stage=2, fast=h["fast"], mid1=h["mid1"],
                           mid2=mid2, mid3="", **rec)
                writer_all.writerow(row.values())
                s2.append(row)
        s2.sort(key=lambda r: (-r[METRIC], -r["expectancy"], r["trades"]))
        heads2, seen = [], set()
        for r in s2:
            if DISTINCT2 and r["mid2"] in seen: continue
            heads2.append(r); seen.add(r["mid2"])
            if len(heads2) >= PASS2_N: break

        # PASS 3: add mid3
        s3 = []
        for h in heads2:
            for mid3 in MID3_LIST:
                if mid3 <= h["mid2"]: continue
                rec = backtest(symbol, h["fast"], h["mid1"], h["mid2"], mid3,
                               ATR_MULT, window["warm"], window["start"], window["end"])
                row = dict(stage=3, fast=h["fast"], mid1=h["mid1"],
                           mid2=h["mid2"], mid3=mid3, **rec)
                writer_all.writerow(row.values())
                s3.append(row)

    # write final top combos
    s3.sort(key=lambda r: (-r[METRIC], -r["expectancy"], r["trades"]))
    with open(out_final, "w", newline="") as f_fin:
        writer_fin = csv.writer(f_fin)
        writer_fin.writerow(["fast","mid1","mid2","mid3",
                             METRIC,"expectancy","trades","win_rate"])
        for r in s3[:PASS3_N]:
            writer_fin.writerow([
                r["fast"], r["mid1"], r["mid2"], r["mid3"],
                f"{r[METRIC]:.6f}", f"{r['expectancy']:.6f}",
                r["trades"], f"{r['win_rate']:.1f}%"
            ])

    print(f"[{symbol} | {window['label']}] Wrote {out_all} & {out_final}")

# ─── main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    for window in WINDOWS:
        for symbol in SYMBOLS:
            print(f"\n====== OPTIMIZING {symbol} | {window['label']} ======")
            optimize_for_window(symbol, window)
