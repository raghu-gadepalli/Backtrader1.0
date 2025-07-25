#!/usr/bin/env python3
# scripts/run_hmamulti_test.py

import os
import sys
from datetime import datetime
import pandas as pd
import backtrader as bt

#  Project root 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

from data.load_candles          import load_candles
from strategies.hma_multitrend  import HmaMultiTrendStrategy
from analyzers.trade_list       import TradeList   # same file used for ST

#  CONFIG 
# Grid of HMA sets to test for RELIANCE (add more symbols/sets as needed)
HMA_PARAM_GRID = {
    "ICICIBANK": [
        {"fast": 120, "mid1": 320, "mid2": 1200,  "mid3": 3800},
        # {"fast": 240, "mid1": 480, "mid2": 960,  "mid3": 1920},
        # {"fast": 260, "mid1": 520, "mid2": 1040, "mid3": 2080},
    ],
    "INFY": [
        {"fast": 120, "mid1": 320, "mid2": 1200,  "mid3": 3800},
        # {"fast": 240, "mid1": 480, "mid2": 960,  "mid3": 1920},
        # {"fast": 260, "mid1": 520, "mid2": 1040, "mid3": 2080},
    ],
    "RELIANCE": [
        {"fast": 120, "mid1": 320, "mid2": 1200,  "mid3": 3800},
        # {"fast": 240, "mid1": 480, "mid2": 960,  "mid3": 1920},
        # {"fast": 260, "mid1": 520, "mid2": 1040, "mid3": 2080},
    ],
}

# Warm-up control
HARD_CAP_FACTOR = 10    # max = fast * 10 bars
MIN_FACTOR      = 3     # warn if < fast * 3
BURN_IN_DATE    = "2024-12-01"

# Windows to evaluate
PERIODS = {
    "Jan-2025":  ("2025-01-01", "2025-01-31"),
    "Feb-2025":  ("2025-02-01", "2025-02-28"),
    "Mar-2025":  ("2025-03-01", "2025-03-31"),
    "Apr-2025":  ("2025-04-01", "2025-04-30"),
    "May-2025":  ("2025-05-01", "2025-05-31"),
    "Jun-2025":  ("2025-06-01", "2025-06-30"),
    "Jul-2025":  ("2025-07-01", "2025-07-17"),
    "All":       ("2024-12-31", "2025-07-17"),
}

STARTING_CASH = 500_000
COMMISSION    = 0.0002

summary_rows = []
trade_rows   = []


def run_period(symbol: str, label: str, start_raw: str, end_raw: str,
               fast: int, mid1: int, mid2: int, mid3: int):
    """Run one test window for one HMA param combo."""
    # 1) Load data
    df_all = load_candles(symbol, BURN_IN_DATE, end_raw)
    df_all.index = pd.to_datetime(df_all.index)

    ts_start = datetime.strptime(start_raw, "%Y-%m-%d")
    ts_end   = datetime.strptime(end_raw,   "%Y-%m-%d")

    df_warm_all = df_all[df_all.index < ts_start]
    df_test     = df_all[(df_all.index >= ts_start) & (df_all.index <= ts_end)]

    # warm-up bars needed
    max_needed = fast * HARD_CAP_FACTOR
    have       = len(df_warm_all)
    needed     = min(max_needed, have)

    if needed < fast * MIN_FACTOR:
        print(f"[WARN] {symbol} {label}: only {have} warm-up bars (<{MIN_FACTOR}x fast).")

    df_warm = df_warm_all.tail(needed)
    df      = pd.concat([df_warm, df_test])

    # 2) Cerebro setup
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)
    cerebro.broker.setcash(STARTING_CASH)
    cerebro.broker.setcommission(commission=COMMISSION)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(TradeList,                  _name="tradelist")

    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(
        HmaMultiTrendStrategy,
        fast=fast, mid1=mid1, mid2=mid2, mid3=mid3,
        printlog=False
    )

    strat = cerebro.run()[0]

    # 3) Summary metrics
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd     = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr     = strat.analyzers.trades.get_analysis()

    won    = tr.get("won",  {}).get("total", 0)
    lost   = tr.get("lost", {}).get("total", 0)
    tot    = tr.get("total",{}).get("closed", 0)
    winr   = (won / tot * 100) if tot else 0.0

    avg_w  = tr.get("won",  {}).get("pnl", {}).get("average", 0.0)
    avg_l  = tr.get("lost", {}).get("pnl", {}).get("average", 0.0)
    expc   = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("nan")

    print(f"\n--- {symbol} | {label} @ HMA({fast},{mid1},{mid2},{mid3}) ---")
    print(f"Warm-up bars: {needed}  (have={have}, cap={max_needed})")
    print(f"Sharpe : {sharpe:.2f}, DD: {dd:.2f}%, Trades: {tot}, Win%: {winr:.1f}%, Exp: {expc:.4f}")

    summary_rows.append({
        "symbol":       symbol,
        "period_label": label,
        "fast":         fast,
        "mid1":         mid1,
        "mid2":         mid2,
        "mid3":         mid3,
        "sharpe":       sharpe,
        "drawdown":     dd,
        "trades":       tot,
        "win_rate":     winr,
        "expectancy":   expc,
    })

    # 4) Detailed trades
    for row in strat.analyzers.tradelist.get_analysis():
        row.update({
            "symbol":       symbol,
            "period_label": label,
            "fast":         fast,
            "mid1":         mid1,
            "mid2":         mid2,
            "mid3":         mid3,
        })
        trade_rows.append(row)


if __name__ == "__main__":
    for sym, cfg_list in HMA_PARAM_GRID.items():
        for cfg in cfg_list:
            for lbl, (s, e) in PERIODS.items():
                run_period(sym, lbl, s, e,
                           fast=cfg["fast"], mid1=cfg["mid1"],
                           mid2=cfg["mid2"], mid3=cfg["mid3"])

    sum_path   = os.path.join(RESULTS_DIR, "hma_multi_test_results.csv")
    trade_path = os.path.join(RESULTS_DIR, "hma_multi_trade_results.csv")

    pd.DataFrame(summary_rows).to_csv(sum_path, index=False)

    for i, r in enumerate(trade_rows, start=1):
        r["tradeid"] = i

    
    cols = [
    "dt_in","dt_out","price_in","price_out","size","side",
    "pnl","pnl_comm","barlen","tradeid",
    "atr_entry","atr_pct","mae_abs","mae_pct",
    "mfe_abs","mfe_pct","ret_pct",
    "symbol","period_label","fast","mid1","mid2","mid3"
    ]

    pd.DataFrame(trade_rows).to_csv(trade_path, index=False)

    print(f"\nWrote {sum_path}")
    print(f"Wrote {trade_path}")
