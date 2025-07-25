#!/usr/bin/env python3
"""
Mirror of run_supertrend_test.py for HMA crossover.
Writes:
  results/hmacr_test_results.csv   (summary)
  results/hmacr_trade_results.csv  (per-trade, includes only atr_entry extra)
"""

import os
import sys
import pandas as pd
from datetime import datetime

#  project root 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles        import load_candles
from strategies.hma_crossover import HmaCrossover
from analyzers.trade_list     import TradeList  # same as SuperTrend run

#  config (keep identical style to supertrend test) 
HMA_PARAM_GRID = [
    {"fast": 120,  "slow": 320,  "atr_mult": 0.0},
    {"fast": 320, "slow": 1200, "atr_mult": 0.0},
    {"fast": 1200, "slow": 3800, "atr_mult": 0.0},
]

# SYMBOLS = ["INFY", "ICICIBANK", "RELIANCE"]  # extend as needed
SYMBOLS = ["RELIANCE"]  # extend as needed

BURN_IN_DATE  = "2024-06-15"
WARMUP_FACTOR = 10   # just so calc matches your ST file; strategy itself blocks pre-start signals

PERIODS = {
    # "Jan-2025":  ("2025-01-01", "2025-01-31"),
    # "Feb-2025":  ("2025-02-01", "2025-02-28"),
    # "Mar-2025":  ("2025-03-01", "2025-03-31"),
    # "Apr-2025":  ("2025-04-01", "2025-04-30"),
    # "May-2025":  ("2025-05-01", "2025-05-31"),
    # "Jun-2025":  ("2025-06-01", "2025-06-30"),
    "Jul-2025":  ("2025-07-01", "2025-07-22"),
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
               atr_period: int,
               atr_mult: float):

    # load ALL data until end_raw, like ST script
    df_all = load_candles(symbol, BURN_IN_DATE, end_raw)
    df_all.index = pd.to_datetime(df_all.index)

    ts_start = datetime.strptime(start_raw, "%Y-%m-%d")
    ts_end   = datetime.strptime(end_raw,   "%Y-%m-%d")

    # warm-up bars (same logic as ST)
    needed = max(fast, slow) * WARMUP_FACTOR
    df_warm = df_all[df_all.index < ts_start]
    df_test = df_all[(df_all.index >= ts_start) & (df_all.index <= ts_end)]

    if len(df_warm) < needed:
        print(f"[WARN] {symbol} {label}: warm-up shortage (need {needed}, have {len(df_warm)}). Using what we have.")

    df = pd.concat([df_warm.tail(needed), df_test])

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

    cerebro.addstrategy(HmaCrossover,
                        fast=fast,
                        slow=slow,
                        atr_period=atr_period,
                        atr_mult=atr_mult,
                        eval_start=ts_start,
                        printlog=False)

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

    print(f"\n--- {symbol} | {label} @ HMA({fast},{slow}) ATRx{atr_mult} ---")
    print(f"Sharpe : {sharpe:.2f}, DD: {dd:.2f}%, Trades: {tot}, Win%: {winr:.1f}%, Exp: {expc:.4f}")

    summary_rows.append({
        "symbol":       symbol,
        "fast":         fast,
        "slow":         slow,
        "atr_mult":     atr_mult,
        "period_label": label,
        "sharpe":       sharpe,
        "drawdown":     dd,
        "trades":       tot,
        "win_rate":     winr,
        "expectancy":   expc,
    })

    # TradeList already has dictionary rows; just add our params and keep only atr_entry extra
    for row in strat.analyzers.tradelist.get_analysis():
        row.update({
            "symbol":       symbol,
            "period_label": label,
            "fast":         fast,
            "slow":         slow,
            "atr_mult":     atr_mult,
        })
        # ensure atr_entry exists (TradeList should read from strategy if you mirrored ST)
        # If not, set to NaN
        row.setdefault("atr_entry", getattr(strat, "last_atr_on_entry", float("nan")))
        trade_rows.append(row)


if __name__ == "__main__":
    for sym in SYMBOLS:
        for cfg in HMA_PARAM_GRID:
            for lbl, (s, e) in PERIODS.items():
                run_period(sym, lbl, s, e,
                           fast=cfg["fast"],
                           slow=cfg["slow"],
                           atr_period=14,
                           atr_mult=cfg["atr_mult"])

    sum_path    = os.path.join(RESULTS_DIR, "hmacr_test_results.csv")
    trades_path = os.path.join(RESULTS_DIR, "hmacr_trade_results.csv")

    pd.DataFrame(summary_rows).to_csv(sum_path, index=False)

    # give each trade a unique id
    for i, r in enumerate(trade_rows, start=1):
        r["tradeid"] = i

    cols = [
        "dt_in","dt_out","price_in","price_out","size","side",
        "pnl","pnl_comm","barlen","tradeid",
        "atr_entry",   # <- only ATR, as requested
        "symbol","period_label","fast","slow","atr_mult"
    ]

    pd.DataFrame(trade_rows)[cols].to_csv(trades_path, index=False)

    print(f"\nWrote {sum_path}")
    print(f"Wrote {trades_path}")
