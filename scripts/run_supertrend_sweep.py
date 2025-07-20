#!/usr/bin/env python3
"""
scripts/run_supertrend_sweep.py

Two‑pass coordinate descent for SuperTrend across multiple symbols:
1) Sweep ATR period (with default mult) → pick top periods
2) Drill multiplier on those periods     → pick final survivors

Writes two merged CSVs into results/:
  - supertrend_opt_all_stages.csv   (stage 1 + stage 2 rows, with symbol)
  - supertrend_opt_final.csv        (final survivors)
"""

import os, sys, csv
from datetime import datetime

# ─── project root ────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles    import load_candles
from strategies.supertrend import ST

# ─── USER PARAMETERS ─────────────────────────────────────────────────────────
SYMBOLS      = ["ICICIBANK", "INFY", "RELIANCE"]
WARMUP_START = "2025-04-01"
END          = "2025-07-06"

# two‑pass grid
ST_PERIODS   = [20, 30, 40, 60]       # ATR lookback
ST_MULTS     = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0] # multiplier
DEFAULT_MULT = ST_MULTS[len(ST_MULTS)//2] # e.g. 6.0

PASS1_N      = 3    # keep top 3 periods
PASS2_N      = 3    # keep top 3 multipliers
DISTINCT1    = True # unique period in pass1
DISTINCT2    = True # unique mult   in pass2

STARTING_CASH   = 500_000
COMMISSION_RATE = 0.0002

def make_cerebro():
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)
    cerebro.broker.setcash(STARTING_CASH)
    cerebro.broker.setcommission(commission=COMMISSION_RATE)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    return cerebro

def backtest(symbol, period, mult):
    """
    Run one SuperTrend backtest; return (sharpe, expectancy, total_trades, win_rate%).
    """
    cerebro = make_cerebro()
    df      = load_candles(symbol, WARMUP_START, END)
    df.index = df.index if hasattr(df, 'index') else df  # ensure datetime index

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

        # PASS 1: sweep ATR periods at DEFAULT_MULT
        p1 = []
        total = len(ST_PERIODS)
        for i, period in enumerate(ST_PERIODS, 1):
            print(f"[{symbol}] P1 {i}/{total} → period={period}, mult={DEFAULT_MULT}")
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
            p1.append(rec)

        # pick top PASS1_N periods
        p1.sort(key=sort_key)
        heads1, seen1 = [], set()
        for r in p1:
            if DISTINCT1 and r["period"] in seen1:
                continue
            heads1.append(r)
            seen1.add(r["period"])
            if len(heads1) >= PASS1_N:
                break

        # PASS 2: for each top period, sweep multipliers
        p2 = []
        for idx, h in enumerate(heads1, 1):
            period = h["period"]
            print(f"[{symbol}] P2 #{idx}/{len(heads1)} → drilling mult on period={period}")
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
                p2.append(rec)

        # pick top PASS2_N (final survivors)
        p2.sort(key=sort_key)
        heads2, seen2 = [], set()
        for r in p2:
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
