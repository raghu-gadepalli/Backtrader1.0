#!/usr/bin/env python3
"""
scripts/run_supertrend_refine.py

Manual refinement for SuperTrend: for one or more symbols, test a hand‑picked
list of (period, mult) combos and both dump results to CSV _and_ print them.
Warm‑up is exactly period*WARMUP_FACTOR bars immediately before TEST_START,
taken from the full load from BURN_IN_DATE→END.
"""

import os
import sys
import csv
import pandas as pd
from datetime import datetime

import backtrader as bt

# ─── project root ────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles    import load_candles
from strategies.supertrend import ST

# ─── SETTINGS ────────────────────────────────────────────────────────────────
BURN_IN_DATE   = "2025-02-15"   # earliest bar you’ll ever load
TEST_START     = "2025-04-01"   # inclusive start of your test window
END            = "2025-07-06"   # inclusive end of test window
STARTING_CASH  = 500_000
COMMISSION     = 0.0002
WARMUP_FACTOR  = 10             # burn‑in bars = period * this factor

# ─── MANUAL COMBINATIONS PER SYMBOL ──────────────────────────────────────────

# auto‑generate period=60, mult from 1.0 to 16.8 inclusive in steps of 0.2
multipliers = [x / 5 for x in range(6, 85)]  # since 1.2*5=6 and 16.8*5=84

COMBINATIONS = {
    # "AXISBANK": [
    #     {"period": 60, "mult": m}
    #     for m in multipliers
    # ],
    # "HDFCBANK": [
    #     {"period": 60, "mult": m}
    #     for m in multipliers
    # ],
    # "KOTAKBANK": [
    #     {"period": 60, "mult": m}
    #     for m in multipliers
    # ],
    # "MARUTI": [
    #     {"period": 60, "mult": m}
    #     for m in multipliers
    # ],
    # "NIFTY 50": [
    #     {"period": 60, "mult": m}
    #     for m in multipliers
    # ],
    # "NIFTY BANK": [
    #     {"period": 60, "mult": m}
    #     for m in multipliers
    # ],
    # "SBIN": [
    #     {"period": 60, "mult": m}
    #     for m in multipliers
    # ],
    # "SUNPHARMA": [
    #     {"period": 60, "mult": m}
    #     for m in multipliers
    # ],
    # "TATAMOTORS": [
    #     {"period": 60, "mult": m}
    #     for m in multipliers
    # ],
    "TCS": [
        {"period": 60, "mult": m}
        for m in multipliers
    ],
    "TECHM": [
        {"period": 60, "mult": m}
        for m in multipliers
    ],
    # add more symbols here if desired...
}

def make_cerebro():
    c = bt.Cerebro(stdstats=False)
    c.broker.set_coc(True)
    c.broker.setcash(STARTING_CASH)
    c.broker.setcommission(commission=COMMISSION)
    c.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                  timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    c.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    return c

def backtest(symbol: str, period: int, mult: float):
    # load full history once
    df_all = load_candles(symbol, BURN_IN_DATE, END)
    df_all.index = pd.to_datetime(df_all.index)

    # split warm‑up vs test
    ts_dt       = datetime.strptime(TEST_START, "%Y-%m-%d")
    df_warm_all = df_all[df_all.index < ts_dt]
    df_test     = df_all[df_all.index >= ts_dt]

    # ensure enough warm‑up bars
    needed = period * WARMUP_FACTOR
    if len(df_warm_all) < needed:
        print(f"❗ Not enough warm‑up bars for {symbol} (have {len(df_warm_all)}, need {needed})")
        sys.exit(1)

    # take exactly the last `needed` bars for warm‑up
    df_warm = df_warm_all.tail(needed)
    # concatenate warm‑up + test
    df = pd.concat([df_warm, df_test])

    # run the backtest
    cerebro = make_cerebro()
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)
    cerebro.addstrategy(ST, st_period=period, st_mult=mult)
    strat = cerebro.run()[0]

    # extract metrics
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

def run_refine():
    outdir = os.path.join(_ROOT, "results")
    os.makedirs(outdir, exist_ok=True)

    for symbol, combos in COMBINATIONS.items():
        out_csv = os.path.join(outdir, f"{symbol}_supertrend_refine.csv")
        print(f"\n=== {symbol} Refinement ===")
        with open(out_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["period","mult","sharpe","expectancy","trades","win_rate"])
            f.flush()

            for combo in combos:
                p, m = combo["period"], combo["mult"]
                sr, expc, tot, wr = backtest(symbol, p, m)

                # write to CSV
                writer.writerow([
                    p, m,
                    f"{sr:.6f}",
                    f"{expc:.6f}" if not pd.isna(expc) else "nan",
                    tot,
                    f"{wr:.2f}"
                ])
                f.flush()

                # print concise result
                print(f"ST({p},{m}) → Sharpe: {sr:.6f}, "
                      f"Expectancy: {expc:.6f}, Trades: {tot}, Win Rate: {wr:.2f}%")

if __name__ == "__main__":
    run_refine()
