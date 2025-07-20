#!/usr/bin/env python3
"""
scripts/run_supertrend_sweep.py

Three‐pass coordinate descent for SuperTrend across multiple symbols:
  1) Sweep ATR period (with default mult)      → pick top periods
  2) Drill coarse multipliers (2→12 step 2)    → pick top multipliers
  3) Refine multipliers (±0.4 step 0.2 around) → pick final survivors

Writes two merged CSVs into results/:
  - supertrend_opt_all_stages.csv   (all pass 1/2/3 rows)
  - supertrend_opt_final.csv        (final top combos per symbol)
"""

import os, sys, csv

# ─── project root ────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles    import load_candles
from strategies.supertrend import ST

# ─── USER PARAMETERS ─────────────────────────────────────────────────────────
SYMBOLS      = ["ICICIBANK", "INFY", "RELIANCE"]
WARMUP_START = "2025-06-25"
END          = "2025-07-17"

# PASS 1: ATR lookback periods
ST_PERIODS   = [20, 30, 40, 60]
# default multiplier for PASS 1
DEFAULT_MULT = 4.0

# PASS 2: coarse multiplier grid
COARSE_MULTS = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
# survivors to carry from pass 1 → pass 2
PASS1_N      = 3

# PASS 3: around each coarse mult, refine ±0.4 in steps of 0.2
# survivors to carry from pass 2 → pass 3
PASS2_N      = 3

# final survivors per symbol
PASS3_N      = 3
# ensure unique picks at each pass
DISTINCT1    = True
DISTINCT2    = True
DISTINCT3    = True

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
    cerebro = make_cerebro()
    df      = load_candles(symbol, WARMUP_START, END)
    data    = bt.feeds.PandasData(dataname=df,
                                  timeframe=bt.TimeFrame.Minutes,
                                  compression=1)
    cerebro.adddata(data)
    cerebro.addstrategy(ST, st_period=period, st_mult=mult)
    strat = cerebro.run()[0]

    sr   = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    tr   = strat.analyzers.trades.get_analysis()
    won  = tr.get("won",{}).get("total", 0)
    lost = tr.get("lost",{}).get("total", 0)
    tot  = won + lost
    avg_w = tr.get("won",{}).get("pnl",{}).get("average", 0.0)
    avg_l = tr.get("lost",{}).get("pnl",{}).get("average", 0.0)
    expc  = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("nan")
    wr    = (won/tot*100) if tot else 0.0

    return sr, expc, tot, wr

def sort_key(r):
    return (-r["sharpe"], -r["expectancy"], r["trades"])

if __name__ == "__main__":
    RESULTS_DIR = os.path.join(_ROOT, "results")
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # all‐stages CSV
    all_path   = os.path.join(RESULTS_DIR, "supertrend_opt_all_stages.csv")
    all_file   = open(all_path, "w", newline="")
    all_writer = csv.writer(all_file)
    all_writer.writerow([
        "symbol","stage","period","mult",
        "sharpe","expectancy","trades","win_rate"
    ])
    all_file.flush()

    # final CSV
    final_path   = os.path.join(RESULTS_DIR, "supertrend_opt_final.csv")
    final_file   = open(final_path, "w", newline="")
    final_writer = csv.writer(final_file)
    final_writer.writerow([
        "symbol","period","mult",
        "sharpe","expectancy","trades","win_rate"
    ])
    final_file.flush()

    for symbol in SYMBOLS:
        print(f"\n====== OPTIMIZING {symbol} ======")

        # PASS 1: sweep periods at DEFAULT_MULT
        p1 = []
        for idx, period in enumerate(ST_PERIODS, 1):
            print(f"[{symbol}] P1 {idx}/{len(ST_PERIODS)} → period={period}, mult={DEFAULT_MULT}")
            sr, expc, tot, wr = backtest(symbol, period, DEFAULT_MULT)
            rec = {"symbol":symbol, "stage":1, "period":period, "mult":DEFAULT_MULT,
                   "sharpe":sr, "expectancy":expc, "trades":tot, "win_rate":wr}
            all_writer.writerow([rec[k] if k in ("symbol","stage","period") else
                                (f"{rec[k]:.6f}" if isinstance(rec[k],float) else rec[k])
                                for k in ["symbol","stage","period","mult","sharpe","expectancy","trades","win_rate"]])
            all_file.flush()
            p1.append(rec)

        # pick top periods
        p1.sort(key=sort_key)
        heads1, seen1 = [], set()
        for r in p1:
            if DISTINCT1 and r["period"] in seen1: continue
            heads1.append(r); seen1.add(r["period"])
            if len(heads1)>=PASS1_N: break

        # PASS 2: sweep coarse multipliers
        p2 = []
        for idx, h in enumerate(heads1,1):
            period = h["period"]
            print(f"[{symbol}] P2 {idx}/{len(heads1)} → drilling coarse mult on period={period}")
            for mult in COARSE_MULTS:
                sr, expc, tot, wr = backtest(symbol, period, mult)
                rec = {"symbol":symbol, "stage":2, "period":period, "mult":mult,
                       "sharpe":sr, "expectancy":expc, "trades":tot, "win_rate":wr}
                all_writer.writerow([rec[k] if k in ("symbol","stage","period") else
                                    (f"{rec[k]:.6f}" if isinstance(rec[k],float) else rec[k])
                                    for k in ["symbol","stage","period","mult","sharpe","expectancy","trades","win_rate"]])
                all_file.flush()
                p2.append(rec)

        # pick top coarse mults
        p2.sort(key=sort_key)
        heads2, seen2 = [], set()
        for r in p2:
            if DISTINCT2 and r["mult"] in seen2: continue
            heads2.append(r); seen2.add(r["mult"])
            if len(heads2)>=PASS2_N: break

        # PASS 3: refine multipliers ±0.4 in 0.2 steps
        for idx, h in enumerate(heads2,1):
            period, base = h["period"], h["mult"]
            refine_mults = [round(base + i*0.2,1) for i in (-2,-1,0,1,2) if base + i*0.2 > 0]
            print(f"[{symbol}] P3 {idx}/{len(heads2)} → refining mults {refine_mults} for period={period}")
            for mult in refine_mults:
                sr, expc, tot, wr = backtest(symbol, period, mult)
                rec = {"symbol":symbol, "stage":3, "period":period, "mult":mult,
                       "sharpe":sr, "expectancy":expc, "trades":tot, "win_rate":wr}
                all_writer.writerow([rec[k] if k in ("symbol","stage","period") else
                                    (f"{rec[k]:.6f}" if isinstance(rec[k],float) else rec[k])
                                    for k in ["symbol","stage","period","mult","sharpe","expectancy","trades","win_rate"]])
                all_file.flush()
                # collect for final selection
                if "p3" not in locals(): p3 = []
                p3.append(rec)

        # pick final survivors from pass 3
        p3.sort(key=sort_key)
        heads3, seen3 = [], set()
        for r in p3:
            if DISTINCT3 and r["mult"] in seen3: continue
            heads3.append(r); seen3.add(r["mult"])
            if len(heads3)>=PASS3_N: break

        # write pass 3 survivors to final CSV
        for r in heads3:
            final_writer.writerow([
                r["symbol"],
                r["period"],
                r["mult"],
                f"{r['sharpe']:.6f}",
                f"{r['expectancy']:.6f}",
                r["trades"],
                f"{r['win_rate']:.2f}"
            ])
            final_file.flush()

        # clear p3 for next symbol
        del p3

    all_file.close()
    final_file.close()
    print(f"\nWrote merged all‑stages → {all_path}")
    print(f"Wrote merged final   → {final_path}")
