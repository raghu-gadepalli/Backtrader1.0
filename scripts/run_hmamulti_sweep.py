#!/usr/bin/env python3
"""
scripts/run_hma_multi_sweep.py

Three-pass coordinate descent for multi-HMA across multiple symbols,
logging **all** stage results and **final** survivors into two merged CSVs
in the results/ folder, with expectancy and incremental flushes.
"""

import os
import sys
import csv

# ─── project root on path ─────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ─── dump CSVs into a 'results' folder ────────────────────────────────────────
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

import backtrader as bt
from data.load_candles         import load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy

# ─── USER PARAMETERS ─────────────────────────────────────────────────────────
SYMBOLS      = ["ICICIBANK", "INFY", "RELIANCE"]
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

# ─── PARAMETER RANGES (COMMON) ───────────────────────────────────────────────
FAST_PERIODS = range(30, 181, 30)
MID1_PERIODS = range(120, 721, 120)
MID2_PERIODS = [120, 180, 240, 360, 840]
MID3_PERIODS = [240, 360, 480, 720]

# ─── Starting capital & commission ───────────────────────────────────────────
REQUIRED_CASH     = 500_000
COMMISSION_RATE   = 0.0002

def make_cerebro():
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)
    cerebro.broker.setcash(REQUIRED_CASH)
    cerebro.broker.setcommission(commission=COMMISSION_RATE)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,  _name="trades")
    return cerebro

def backtest(symbol, fast, mid1, mid2, mid3, atr_mult):
    cerebro = make_cerebro()
    df      = load_candles(symbol, WARMUP_START, END)
    data    = bt.feeds.PandasData(dataname=df,
                                  timeframe=bt.TimeFrame.Minutes,
                                  compression=1)
    cerebro.adddata(data)
    cerebro.addstrategy(HmaMultiTrendStrategy,
                        fast=fast, mid1=mid1, mid2=mid2, mid3=mid3,
                        atr_mult=atr_mult, printlog=False)

    strat = cerebro.run()[0]
    # Sharpe
    s   = strat.analyzers.sharpe.get_analysis().get("sharperatio") or float("-inf")
    # Trades
    tr  = strat.analyzers.trades.get_analysis()
    won = tr.get("won",{}).get("total",0)
    lost= tr.get("lost",{}).get("total",0)
    # Expectancy
    avg_w = tr.get("won",{}).get("pnl",{}).get("average",0.0)
    avg_l = tr.get("lost",{}).get("pnl",{}).get("average",0.0)
    tot   = won + lost
    e     = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("-inf")
    return s, e, won, lost

def sort_key(r):
    return (-r[METRIC], -r["expectancy"], r["trades"])

if __name__ == "__main__":
    # Open merged 'all stages' CSV
    all_path = os.path.join(RESULTS_DIR, "hma_multi_opt_all_stages.csv")
    all_file = open(all_path, "w", newline="")
    all_writer = csv.writer(all_file)
    all_writer.writerow([
        "symbol","stage","fast","mid1","mid2","mid3",
        "sharpe","expectancy","trades","win_rate"
    ])
    all_file.flush()

    # Open merged 'final survivors' CSV
    final_path = os.path.join(RESULTS_DIR, "hma_multi_opt_final.csv")
    final_file = open(final_path, "w", newline="")
    final_writer = csv.writer(final_file)
    final_writer.writerow([
        "symbol","fast","mid1","mid2","mid3",
        "sharpe","expectancy","trades","win_rate"
    ])
    final_file.flush()

    for symbol in SYMBOLS:
        print(f"\n====== OPTIMIZING {symbol} ======")
        # --- PASS 1: fast & mid1 ---
        s1_results = []
        total = sum(1 for f in FAST_PERIODS for m1 in MID1_PERIODS if f < m1)
        cnt = 0
        print(f"[{symbol}] PASS 1: sweeping fast & mid1")
        for fast in FAST_PERIODS:
            for mid1 in MID1_PERIODS:
                if fast >= mid1: continue
                cnt += 1
                def_mid2, def_mid3 = fast*2, fast*4
                s,e,won,lost = backtest(symbol, fast, mid1, def_mid2, def_mid3, ATR_MULT)
                trades = won + lost
                wr     = (won/trades*100) if trades else 0
                print(f" [{cnt}/{total}] f={fast} m1={mid1}  SR={s:.2f} Exp={e:.2f}")
                rec = {
                    "symbol":    symbol,
                    "stage":     1,
                    "fast":      fast,
                    "mid1":      mid1,
                    "mid2":      def_mid2,
                    "mid3":      def_mid3,
                    "sharpe":    s,
                    "expectancy":e,
                    "trades":    trades,
                    "win_rate":  wr,
                }
                all_writer.writerow([
                    rec["symbol"], rec["stage"], rec["fast"], rec["mid1"],
                    rec["mid2"], rec["mid3"], f"{s:.6f}",
                    f"{e:.6f}", rec["trades"], f"{wr:.2f}"
                ])
                all_file.flush()
                s1_results.append(rec)

        # pick pass1 survivors
        s1_results.sort(key=sort_key)
        heads1, seen1 = [], set()
        for r in s1_results:
            if DISTINCT1 and r["fast"] in seen1: continue
            heads1.append(r); seen1.add(r["fast"])
            if len(heads1) >= PASS1_N: break

        # --- PASS 2: mid2 on survivors ---
        s2_results = []
        total = sum(1 for h in heads1 for m2 in MID2_PERIODS if m2 > h["mid1"])
        cnt = 0
        print(f"[{symbol}] PASS 2: drilling mid2 ({len(heads1)} survivors)")
        for h in heads1:
            fast, mid1 = h["fast"], h["mid1"]
            for mid2 in MID2_PERIODS:
                if mid2 <= mid1: continue
                cnt += 1
                def_mid3 = fast*4
                s,e,won,lost = backtest(symbol, fast, mid1, mid2, def_mid3, ATR_MULT)
                trades = won + lost
                wr     = (won/trades*100) if trades else 0
                rec = {
                    "symbol":    symbol,
                    "stage":     2,
                    "fast":      fast,
                    "mid1":      mid1,
                    "mid2":      mid2,
                    "mid3":      def_mid3,
                    "sharpe":    s,
                    "expectancy":e,
                    "trades":    trades,
                    "win_rate":  wr,
                }
                all_writer.writerow([
                    rec["symbol"], rec["stage"], rec["fast"], rec["mid1"],
                    rec["mid2"], rec["mid3"], f"{s:.6f}",
                    f"{e:.6f}", rec["trades"], f"{wr:.2f}"
                ])
                all_file.flush()
                s2_results.append(rec)

        # pick pass2 survivors
        s2_results.sort(key=sort_key)
        heads2, seen2 = [], set()
        for r in s2_results:
            if DISTINCT2 and r["mid2"] in seen2: continue
            heads2.append(r); seen2.add(r["mid2"])
            if len(heads2) >= PASS2_N: break

        # --- PASS 3: mid3 on survivors ---
        s3_results = []
        total = sum(1 for h in heads2 for m3 in MID3_PERIODS if m3 > h["mid2"])
        cnt = 0
        print(f"[{symbol}] PASS 3: drilling mid3 ({len(heads2)} survivors)")
        for h in heads2:
            fast, mid1, mid2 = h["fast"], h["mid1"], h["mid2"]
            for mid3 in MID3_PERIODS:
                if mid3 <= mid2: continue
                cnt += 1
                s,e,won,lost = backtest(symbol, fast, mid1, mid2, mid3, ATR_MULT)
                trades = won + lost
                wr     = (won/trades*100) if trades else 0
                rec = {
                    "symbol":    symbol,
                    "stage":     3,
                    "fast":      fast,
                    "mid1":      mid1,
                    "mid2":      mid2,
                    "mid3":      mid3,
                    "sharpe":    s,
                    "expectancy":e,
                    "trades":    trades,
                    "win_rate":  wr,
                }
                all_writer.writerow([
                    rec["symbol"], rec["stage"], rec["fast"], rec["mid1"],
                    rec["mid2"], rec["mid3"], f"{s:.6f}",
                    f"{e:.6f}", rec["trades"], f"{wr:.2f}"
                ])
                all_file.flush()
                s3_results.append(rec)

        # pick final survivors and write to final CSV
        s3_results.sort(key=sort_key)
        heads3, seen3 = [], set()
        for r in s3_results:
            if DISTINCT3 and r["mid3"] in seen3: continue
            heads3.append(r); seen3.add(r["mid3"])
            if len(heads3) >= PASS3_N: break

        for r in heads3:
            final_writer.writerow([
                r["symbol"],
                r["fast"], r["mid1"], r["mid2"], r["mid3"],
                f"{r['sharpe']:.6f}", f"{r['expectancy']:.6f}",
                r["trades"], f"{r['win_rate']:.2f}"
            ])
            final_file.flush()

    all_file.close()
    final_file.close()
    print(f"\nWrote merged all‑stages → {all_path}")
    print(f"Wrote merged final survivors → {final_path}")
