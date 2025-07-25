#!/usr/bin/env python3
"""
Run MACD tests the same way we do SuperTrend:
   warm-up tail based on factor
   per-period loops
   writes summary & trade CSVs
Requires:
  * analyzers/trade_list.py present (same one used by ST)
  * strategies/macd.py (this file) in your PYTHONPATH
"""

import os
import sys
import pandas as pd
from datetime import datetime

#  Project root fix 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles import load_candles
from strategies.macd    import MACDStrategy
from analyzers.trade_list import TradeList

#  Config 
MACD_PARAM_GRID = [
    {"fast": 120, "slow": 240, "signal": 60,  "hist_thresh": 0.00075},
    # add more combos if you like
]

SYMBOLS = ["RELIANCE"]   # extend

BURN_IN_DATE  = "2024-12-01"
WARMUP_FACTOR = 10

PERIODS = {
    "Jan-2025":  ("2025-01-01", "2025-01-31"),
    "Feb-2025":  ("2025-02-01", "2025-02-28"),
    "Mar-2025":  ("2025-03-01", "2025-03-31"),
    "Apr-2025":  ("2025-04-01", "2025-04-30"),
    "May-2025":  ("2025-05-01", "2025-05-31"),
    "June-2025": ("2025-06-01", "2025-06-30"),
    "July-2025": ("2025-07-01", "2025-07-17"),
    # "All-Period": ("2024-12-31", "2025-07-17"),
}

RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

summary_rows = []
trade_rows   = []


def run_period(symbol: str,
               label: str,
               start_raw: str,
               end_raw: str,
               fast: int,
               slow: int,
               signal: int,
               hist_thresh: float):
    """Single window + config"""
    df_all = load_candles(symbol, BURN_IN_DATE, end_raw)
    df_all.index = pd.to_datetime(df_all.index)

    ts_start = datetime.strptime(start_raw, "%Y-%m-%d")
    ts_end   = datetime.strptime(end_raw,   "%Y-%m-%d")

    df_warm_all = df_all[df_all.index < ts_start]
    df_test     = df_all[(df_all.index >= ts_start) & (df_all.index <= ts_end)]

    needed = max(fast, slow, signal) * WARMUP_FACTOR
    if len(df_warm_all) < needed:
        raise RuntimeError(f"[{symbol} {label}] Warm-up too short (need {needed}, have {len(df_warm_all)})")

    df = pd.concat([df_warm_all.tail(needed), df_test])

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)
    cerebro.broker.setcash(500_000)
    cerebro.broker.setcommission(commission=0.0002)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe", timeframe=bt.TimeFrame.Minutes)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(TradeList,                  _name="tradelist")

    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(MACDStrategy,
                        fast=fast, slow=slow, signal=signal,
                        hist_thresh=hist_thresh,
                        eval_start=ts_start)

    strat = cerebro.run()[0]

    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd     = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr     = strat.analyzers.trades.get_analysis()
    won    = tr.get("won",   {}).get("total", 0)
    lost   = tr.get("lost",  {}).get("total", 0)
    tot    = tr.get("total", {}).get("closed", 0)
    winr   = (won / tot * 100) if tot else 0.0
    avg_w  = tr.get("won",  {}).get("pnl", {}).get("average", 0.0)
    avg_l  = tr.get("lost", {}).get("pnl", {}).get("average", 0.0)
    expc   = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("nan")

    print(f"\n--- {symbol} | {label} @ MACD({fast},{slow},{signal}) ---")
    print(f"Sharpe : {sharpe:.2f}, DD: {dd:.2f}%, Trades: {tot}, Win%: {winr:.1f}%, Exp: {expc:.4f}")

    summary_rows.append({
        "symbol":       symbol,
        "fast":         fast,
        "slow":         slow,
        "signal":       signal,
        "hist_thresh":  hist_thresh,
        "period_label": label,
        "sharpe":       sharpe,
        "drawdown":     dd,
        "trades":       tot,
        "win_rate":     winr,
        "expectancy":   expc,
    })

    for row in strat.analyzers.tradelist.get_analysis():
        row.update({
            "symbol":       symbol,
            "fast":         fast,
            "slow":         slow,
            "signal":       signal,
            "hist_thresh":  hist_thresh,
            "period_label": label,
        })
        trade_rows.append(row)


if __name__ == "__main__":
    for sym in SYMBOLS:
        for cfg in MACD_PARAM_GRID:
            for lbl, (s, e) in PERIODS.items():
                run_period(sym, lbl, s, e,
                           fast=cfg["fast"], slow=cfg["slow"],
                           signal=cfg["signal"], hist_thresh=cfg["hist_thresh"])

    sum_path    = os.path.join(RESULTS_DIR, "macd_test_results.csv")
    trades_path = os.path.join(RESULTS_DIR, "macd_trade_results.csv")

    pd.DataFrame(summary_rows).to_csv(sum_path, index=False)

    for i, r in enumerate(trade_rows, start=1):
        r["tradeid"] = i

    cols = [
        "dt_in","dt_out","price_in","price_out","size","side",
        "pnl","pnl_comm","barlen","tradeid",
        "atr_entry","atr_pct","mae_abs","mae_pct",
        "mfe_abs","mfe_pct","ret_pct",
        "symbol","period_label","fast","slow","signal"
    ]

    pd.DataFrame(trade_rows)[cols].to_csv(trades_path, index=False)

    print(f"\nWrote {sum_path}")
    print(f"Wrote {trades_path}")
