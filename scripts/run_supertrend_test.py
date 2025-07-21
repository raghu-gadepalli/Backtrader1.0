# scripts/run_supertrend_test.py

#!/usr/bin/env python3
"""
Evaluate finalized SuperTrend params on multiple held‑out windows,
using the same BURN_IN → TEST_START split as sweep/refine.
Generates results/supertrend_test_results.csv
"""

import os, sys, pandas as pd
from datetime import datetime

# ─── project root ────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


import backtrader as bt
from data.load_candles    import load_candles
from strategies.supertrend import ST

# ─── SETTINGS ────────────────────────────────────────────────────────────────
ST_PARAMS     = {
    "ICICIBANK": dict(period=60, mult=9.0),
    # "INFY":      dict(period=60, mult=14.0),
    # "RELIANCE":  dict(period=60, mult=7.6),
}
BURN_IN_DATE  = "2025-02-15"
WARMUP_FACTOR = 10

# Define test windows here:
PERIODS = {
    "May-2025":  ("2025-05-01", "2025-05-31"),
    "June-2025": ("2025-06-01", "2025-06-30"),
    "July-2025": ("2025-07-01", "2025-07-17"),
}

RESULTS_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

results = []

def run_period(symbol, label, start_raw, end_raw):
    params = ST_PARAMS[symbol]
    period = params["period"]
    mult   = params["mult"]

    # 1) load full history
    df_all = load_candles(symbol, BURN_IN_DATE, end_raw)
    df_all.index = pd.to_datetime(df_all.index)

    # 2) split warm‑up vs test by start_raw
    ts_dt       = datetime.strptime(start_raw, "%Y-%m-%d")
    df_warm_all = df_all[df_all.index < ts_dt]
    df_test     = df_all[df_all.index >= ts_dt]

    needed = period * WARMUP_FACTOR
    if len(df_warm_all) < needed:
        print(f"❗ Not enough warm‑up for {symbol}@{label} ({len(df_warm_all)} < {needed})")
        sys.exit(1)

    df_warm = df_warm_all.tail(needed)
    df      = pd.concat([df_warm, df_test])

    # 3) run cerebro
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)
    cerebro.broker.setcash(500_000)
    cerebro.broker.setcommission(commission=0.0002)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)
    cerebro.addstrategy(ST, st_period=period, st_mult=mult)
    strat = cerebro.run()[0]

    # 4) collect
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio",0.0) or 0.0
    dd     = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr     = strat.analyzers.trades.get_analysis()
    won    = tr.get("won",{}).get("total",0)
    lost   = tr.get("lost",{}).get("total",0)
    tot    = tr.get("total",{}).get("closed",0)
    winr   = (won/tot*100) if tot else 0.0
    avg_w  = tr.get("won",{}).get("pnl",{}).get("average",0.0)
    avg_l  = tr.get("lost",{}).get("pnl",{}).get("average",0.0)
    expc   = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("nan")

    print(f"\n--- {symbol} | {label} @ ST({period},{mult}) ---")
    print(f"Sharpe : {sharpe:.2f}, DD: {dd:.2f}%, Trades: {tot}, Win%: {winr:.1f}%, Exp: {expc:.4f}")

    results.append({
        "symbol":      symbol,
        "period":      period,
        "mult":        mult,
        "period_label":label,
        "sharpe":      sharpe,
        "drawdown":    dd,
        "trades":      tot,
        "win_rate":    winr,
        "expectancy":  expc,
    })

if __name__ == "__main__":
    for sym, (p,m) in ST_PARAMS.items():
        for label, (s,e) in PERIODS.items():
            run_period(sym, label, s, e)

    out = os.path.join(RESULTS_DIR, "supertrend_test_results.csv")
    pd.DataFrame(results).to_csv(out, index=False)
    print(f"\nWrote {out}")
