#!/usr/bin/env python3
"""
scripts/run_supertrend_refine.py

Manual refinement for SuperTrend: for one or more symbols, test a hand‑picked
list of (period, mult) combos and dump results to
results/<SYMBOL>_supertrend_refine.csv with expectancy.
"""

import os, sys, csv

# ─── project root ────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles    import load_candles
from strategies.supertrend import ST

# ─── SETTINGS ────────────────────────────────────────────────────────────────
WARMUP_START  = "2025-04-01"
END           = "2025-07-06"
STARTING_CASH = 500_000
COMMISSION    = 0.0002

# ─── MANUAL COMBINATIONS PER SYMBOL ──────────────────────────────────────────
# Only include symbols and combos you wish to refine here.
COMBINATIONS = {
    "ICICIBANK": [
        {"period": 30, "mult": 12.0},
        {"period": 40, "mult": 10.0},
        {"period": 20, "mult":  8.0},
    ],
    "INFY": [
        {"period": 30, "mult":  6.0},
        {"period": 50, "mult":  8.0},
    ],
    # add more...
}

def make_cerebro():
    c = bt.Cerebro(stdstats=False)
    c.broker.set_coc(True)
    c.broker.setcash(STARTING_CASH)
    c.broker.setcommission(commission=COMMISSION)
    c.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                  timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    c.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    return c

def backtest(symbol, period, mult):
    """
    Returns (sharpe, expectancy, total_trades, win_rate%).
    """
    cerebro = make_cerebro()
    df      = load_candles(symbol, WARMUP_START, END)
    data    = bt.feeds.PandasData(
        dataname    = df,
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1
    )
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

def run_refine():
    RESULTS_DIR = os.path.join(_ROOT, "results")
    os.makedirs(RESULTS_DIR, exist_ok=True)

    for symbol, combos in COMBINATIONS.items():
        out_csv = os.path.join(RESULTS_DIR, f"{symbol}_supertrend_refine.csv")
        print(f"\nRefining {symbol} → {out_csv}")
        with open(out_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "period","mult","sharpe","expectancy","trades","win_rate"
            ])
            f.flush()

            for c in combos:
                p, m = c["period"], c["mult"]
                print(f"  Testing ST({p},{m}) …")
                sr, expc, tot, wr = backtest(symbol, p, m)
                writer.writerow([
                    p, m,
                    f"{sr:.6f}", f"{expc:.6f}",
                    tot, f"{wr:.2f}"
                ])
                f.flush()

if __name__ == "__main__":
    run_refine()
