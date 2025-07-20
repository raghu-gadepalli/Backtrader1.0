#!/usr/bin/env python3
"""
scripts/run_supertrend_sweep.py

Two‑pass coordinate descent for SuperTrend over multiple symbols:
  1) Sweep ATR period (with default mult) → pick top periods
  2) Drill multiplier on those periods    → pick final survivors

Writes two merged CSVs into results/:
  - supertrend_opt_all_stages.csv   (all pass 1/2 rows, with expectancy)
  - supertrend_opt_final.csv        (top PASS2_N combos per symbol)
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

# two‑pass grid: ATR periods and multipliers
ST_PERIODS   = [20, 30, 40, 60]          # your chosen periods
ST_MULTS     = [2.0, 3.0, 4.0, 5.0, 6.0] # suggested multipliers; adjust as needed
DEFAULT_MULT = ST_MULTS[len(ST_MULTS)//2]  # e.g. 4.0

PASS1_N   = 3    # survivors to drill multiplier
PASS2_N   = 3    # final survivors to output
DISTINCT1 = True # unique period in pass1
DISTINCT2 = True # unique mult   in pass2

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
    df.index = df.index  # ensure datetime index

    data = bt.feeds.PandasData(
        dataname    = df,
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1
    )
    cerebro.adddata(data)
    cerebro.addstrategy(ST, st_period=period, st_mult=mult)

    strat = cerebro.run()[0]
    # Sharpe
    sr   = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    # Trades
    tr   = strat.analyzers.trades.get_analysis()
    won  = tr.get("won",{}).get("total", 0)
    lost = tr.get("lost",{}).get("total", 0)
    tot  = won + lost
    # Expectancy
    avg_w = tr.get("won",{}).get("pnl",{}).get("average", 0.0)
    avg_l = tr.get("lost",{}).get("pnl",{}).get("average", 0.0)
    expc  = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("nan")
    # Win rate %
    wr    = (won/tot*100) if tot else 0.0

    return sr, expc, tot, wr

def sort_key(r):
    # primary: sharpe desc, secondary: expectancy desc, tertiary: trades asc
    return (-r["sharpe"], -r["expectancy"], r["trades"])

if __name__ == "__main__":
    # prepare results folder
    RESULTS_DIR = os.path.join(_ROOT, "results")
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # open merged “all stages” CSV
    all_path   = os.path.join(RESULTS_DIR, "supertrend_opt_all_stages.csv")
    all_file   = open(all_path, "w", newline="")
    all_writer = csv.writer(all_file)
    all_writer.writerow([
        "symbol","stage","period","mult",
        "sharpe","expectancy","trades","win_rate"
    ])
    all_file.flush()

    # open merged “final” CSV
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

        # PASS 1: sweep ATR periods with DEFAULT_MULT
        p1_results = []
        for i, period in enumerate(ST_PERIODS, 1):
            print(f"[{symbol}] PASS 1 {i}/{len(ST_PERIODS)} → period={period}, mult={DEFAULT_MULT}")
            sr, expc, tot, wr = backtest(symbol, period, DEFAULT_MULT)
            rec = {
                "symbol":     symbol,
                "stage":      1,
                "period":     period,
                "mult":       DEFAULT_MULT,
                "sharpe":     sr,
                "expectancy": expc,
                "trades":     tot,
                "win_rate":   wr,
            }
            all_writer.writerow([
                rec["symbol"], rec["stage"], rec["period"], rec["mult"],
                f"{sr:.6f}", f"{expc:.6f}", rec["trades"], f"{wr:.2f}"
            ])
            all_file.flush()
            p1_results.append(rec)

        # pick top PASS1_N periods
        p1_results.sort(key=sort_key)
        heads1, seen1 = [], set()
        for r in p1_results:
            if DISTINCT1 and r["period"] in seen1:
                continue
            heads1.append(r)
            seen1.add(r["period"])
            if len(heads1) >= PASS1_N:
                break

        # PASS 2: drill multipliers on survivors
        p2_results = []
        for idx, h in enumerate(heads1, 1):
            period = h["period"]
            print(f"[{symbol}] PASS 2 #{idx}/{len(heads1)} → drilling mult on period={period}")
            for mult in ST_MULTS:
                print(f"    mult={mult}")
                sr, expc, tot, wr = backtest(symbol, period, mult)
                rec = {
                    "symbol":     symbol,
                    "stage":      2,
                    "period":     period,
                    "mult":       mult,
                    "sharpe":     sr,
                    "expectancy": expc,
                    "trades":     tot,
                    "win_rate":   wr,
                }
                all_writer.writerow([
                    rec["symbol"], rec["stage"], rec["period"], rec["mult"],
                    f"{sr:.6f}", f"{expc:.6f}", rec["trades"], f"{wr:.2f}"
                ])
                all_file.flush()
                p2_results.append(rec)

        # pick top PASS2_N final survivors
        p2_results.sort(key=sort_key)
        heads2, seen2 = [], set()
        for r in p2_results:
            if DISTINCT2 and r["mult"] in seen2:
                continue
            heads2.append(r)
            seen2.add(r["mult"])
            if len(heads2) >= PASS2_N:
                break

        # write final survivors
        for r in heads2:
            final_writer.writerow([
                r["symbol"], r["period"], r["mult"],
                f"{r['sharpe']:.6f}", f"{r['expectancy']:.6f}",
                r["trades"], f"{r['win_rate']:.2f}"
            ])
            final_file.flush()

    all_file.close()
    final_file.close()
    print(f"\nWrote merged all‑stages → {all_path}")
    print(f"Wrote merged final   → {final_path}")
