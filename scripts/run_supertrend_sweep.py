#!/usr/bin/env python3
"""
scripts/run_supertrend_sweep.py

Three‐pass coordinate descent for SuperTrend across multiple symbols,
using a unified warm‑up/test split, with detailed print statements.

Loads from BURN_IN_DATE→END, then:
  - Warm‑up = last period*WARMUP_FACTOR bars before TEST_START
  - Test    = all bars from TEST_START→END

Writes:
  results/supertrend_opt_all_stages.csv
  results/supertrend_opt_final.csv
"""

import os
import sys
import csv
import pandas as pd
from datetime import datetime

# ─── project root ────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


import backtrader as bt
from data.load_candles    import load_candles
from strategies.supertrend import ST

# ─── USER PARAMETERS ─────────────────────────────────────────────────────────
SYMBOLS       = ["ICICIBANK", "INFY", "RELIANCE"]
BURN_IN_DATE  = "2025-02-15"     # earliest bar you’ll ever load
TEST_START    = "2025-06-25"     # start of test window (inclusive)
END           = "2025-07-17"     # end of test window (inclusive)
WARMUP_FACTOR = 10               # warm‑up bars = period * this factor

ST_PERIODS    = [20, 30, 40, 60]
DEFAULT_MULT  = 4.0
COARSE_MULTS  = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
PASS1_N, PASS2_N, PASS3_N = 3, 3, 3
DISTINCT1, DISTINCT2, DISTINCT3 = True, True, True

STARTING_CASH   = 500_000
COMMISSION_RATE = 0.0002

def make_cerebro():
    c = bt.Cerebro(stdstats=False)
    c.broker.set_coc(True)
    c.broker.setcash(STARTING_CASH)
    c.broker.setcommission(commission=COMMISSION_RATE)
    c.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                  timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    c.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    return c

def backtest(symbol, period, mult):
    # Load full history
    df_all = load_candles(symbol, BURN_IN_DATE, END)
    df_all.index = pd.to_datetime(df_all.index)
    # Split warm‑up vs test
    ts_dt       = datetime.strptime(TEST_START, "%Y-%m-%d")
    df_warm_all = df_all[df_all.index < ts_dt]
    df_test     = df_all[df_all.index >= ts_dt]

    needed = period * WARMUP_FACTOR
    if len(df_warm_all) < needed:
        print(f"❗ Not enough warm‑up bars for {symbol} @ period={period}"
              f" (have {len(df_warm_all)}, need {needed})")
        sys.exit(1)

    df_warm = df_warm_all.tail(needed)
    df      = pd.concat([df_warm, df_test])

    cerebro = make_cerebro()
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data)
    cerebro.addstrategy(ST, st_period=period, st_mult=mult)
    strat = cerebro.run()[0]

    sr   = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    tr   = strat.analyzers.trades.get_analysis()
    won  = tr.get("won",{}).get("total",0)
    lost = tr.get("lost",{}).get("total",0)
    tot  = won + lost
    avg_w = tr.get("won",{}).get("pnl",{}).get("average",0.0)
    avg_l = tr.get("lost",{}).get("pnl",{}).get("average",0.0)
    expc  = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("nan")
    wr    = (won/tot*100) if tot else 0.0

    return sr, expc, tot, wr

def sort_key(r):
    return (-r["sharpe"], -r["expectancy"], r["trades"])

if __name__ == "__main__":
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    RESULTS_DIR = os.path.join(ROOT, "results")
    os.makedirs(RESULTS_DIR, exist_ok=True)

    all_path   = os.path.join(RESULTS_DIR, "supertrend_opt_all_stages.csv")
    final_path = os.path.join(RESULTS_DIR, "supertrend_opt_final.csv")

    with open(all_path,  "w", newline="") as all_f, \
         open(final_path,"w", newline="") as fin_f:

        all_w = csv.writer(all_f)
        fin_w = csv.writer(fin_f)

        all_w.writerow(["symbol","stage","period","mult","sharpe",
                        "expectancy","trades","win_rate"])
        fin_w.writerow(["symbol","period","mult","sharpe",
                        "expectancy","trades","win_rate"])

        for symbol in SYMBOLS:
            print(f"\n====== OPTIMIZING {symbol} ======")

            # ── PASS 1: sweep periods ────────────────────────
            p1_results = []
            total1 = len(ST_PERIODS)
            for i, period in enumerate(ST_PERIODS, 1):
                print(f"[{symbol}] PASS1 ({i}/{total1}) → period={period}, mult={DEFAULT_MULT}")
                sr, ex, tot, wr = backtest(symbol, period, DEFAULT_MULT)
                print(f"  → Sharpe={sr:.4f}, Exp={ex:.4f}, Trades={tot}, Win%={wr:.2f}")
                rec = dict(symbol=symbol, stage=1,
                           period=period, mult=DEFAULT_MULT,
                           sharpe=sr, expectancy=ex,
                           trades=tot, win_rate=wr)
                all_w.writerow([symbol,1,period,DEFAULT_MULT,
                                f"{sr:.6f}",f"{ex:.6f}",tot,f"{wr:.2f}"])
                all_f.flush()
                p1_results.append(rec)

            p1_results.sort(key=sort_key)
            heads1, seen = [], set()
            for r in p1_results:
                if DISTINCT1 and r["period"] in seen: continue
                heads1.append(r); seen.add(r["period"])
                if len(heads1) >= PASS1_N: break

            # ── PASS 2: drill coarse multipliers ─────────────
            p2_results = []
            for idx, h in enumerate(heads1, 1):
                print(f"[{symbol}] PASS2 ({idx}/{len(heads1)}) → period={h['period']}")
                for j, m in enumerate(COARSE_MULTS, 1):
                    print(f"  → mult={m}")
                    sr, ex, tot, wr = backtest(symbol, h["period"], m)
                    print(f"     Sharpe={sr:.4f}, Exp={ex:.4f}, Trades={tot}, Win%={wr:.2f}")
                    rec = dict(symbol=symbol, stage=2,
                               period=h["period"], mult=m,
                               sharpe=sr, expectancy=ex,
                               trades=tot, win_rate=wr)
                    all_w.writerow([symbol,2,h["period"],m,
                                    f"{sr:.6f}",f"{ex:.6f}",tot,f"{wr:.2f}"])
                    all_f.flush()
                    p2_results.append(rec)

            p2_results.sort(key=sort_key)
            heads2, seen = [], set()
            for r in p2_results:
                if DISTINCT2 and r["mult"] in seen: continue
                heads2.append(r); seen.add(r["mult"])
                if len(heads2) >= PASS2_N: break

            # ── PASS 3: refine multipliers ±0.4 step 0.2 ─────
            p3_results = []
            for idx, h in enumerate(heads2, 1):
                base = h["mult"]
                refine = [round(base + dm,1) for dm in (-0.4,-0.2,0,0.2,0.4) if base+dm>0]
                print(f"[{symbol}] PASS3 ({idx}/{len(heads2)}) → refine mults={refine}")
                for m in refine:
                    print(f"  → mult={m}")
                    sr, ex, tot, wr = backtest(symbol, h["period"], m)
                    print(f"     Sharpe={sr:.4f}, Exp={ex:.4f}, Trades={tot}, Win%={wr:.2f}")
                    rec = dict(symbol=symbol, stage=3,
                               period=h["period"], mult=m,
                               sharpe=sr, expectancy=ex,
                               trades=tot, win_rate=wr)
                    all_w.writerow([symbol,3,h["period"],m,
                                    f"{sr:.6f}",f"{ex:.6f}",tot,f"{wr:.2f}"])
                    all_f.flush()
                    p3_results.append(rec)

            p3_results.sort(key=sort_key)
            heads3, seen = [], set()
            for r in p3_results:
                if DISTINCT3 and r["mult"] in seen: continue
                heads3.append(r); seen.add(r["mult"])
                if len(heads3) >= PASS3_N: break

            # write final survivors
            for r in heads3:
                print(f"[{symbol}] FINAL → period={r['period']}, mult={r['mult']}, "
                      f"Sharpe={r['sharpe']:.4f}, Exp={r['expectancy']:.4f}")
                fin_w.writerow([symbol,
                                r["period"],r["mult"],
                                f"{r['sharpe']:.6f}",
                                f"{r['expectancy']:.6f}",
                                r["trades"],f"{r['win_rate']:.2f}"])
                fin_f.flush()

    print(f"\nWrote all‑stages → {all_path}")
    print(f"Wrote final       → {final_path}")
