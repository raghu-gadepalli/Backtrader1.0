#!/usr/bin/env python3
"""
Run ATR-bucket switching HMA strategy (HmaSwitcher) for a given date window.

Outputs (in results/):
  switch_summary.csv   -> Sharpe, DD, trades, win%, expectancy, R_mean
  switch_trades.csv    -> TradeList rows
"""

import os, sys
import pandas as pd
from datetime import datetime
from pathlib import Path

#  project root 
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import backtrader as bt
from data.load_candles         import load_candles
from strategies.hma_switcher   import HmaSwitcher
from analyzers.trade_list      import TradeList

#  Hard-coded ATR percentiles & lookup (from your analysis) 
PCTS = {
    "INFY":      {"P25": 1.078448, "P50": 1.397332, "P75": 1.837079},
    "RELIANCE":  {"P25": 0.755430, "P50": 0.929390, "P75": 1.217022},
    "ICICIBANK": {"P25": 0.775284, "P50": 0.965120, "P75": 1.222725},
}
LOOKUP = {
    "INFY":      {"ATR<P25":"200x300","P25P50":"200x300","P50P75":"120x180",">=P75":"200x300"},
    "RELIANCE":  {"ATR<P25":"120x180","P25P50":"200x300","P50P75":"120x180",">=P75":"60x90"},
    "ICICIBANK": {"ATR<P25":"60x90",  "P25P50":"120x180","P50P75":"60x90",  ">=P75":"120x180"},
}

SYMBOLS = ["INFY", "RELIANCE", "ICICIBANK"]
START   = "2025-07-01"
END     = "2025-07-22"
BURN_IN = "2024-06-15"   # feed history for indicators
RESULTS = _ROOT / "results"
RESULTS.mkdir(exist_ok=True)

summary_rows = []
trade_rows   = []

def run_symbol(symbol):
    df_all = load_candles(symbol, BURN_IN, END)
    df_all.index = pd.to_datetime(df_all.index)

    ts_start = datetime.strptime(START, "%Y-%m-%d")
    ts_end   = datetime.strptime(END,   "%Y-%m-%d")

    # Just feed until end; strategy itself uses full bars
    df = df_all[df_all.index <= ts_end]

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)
    cerebro.broker.setcash(500_000)
    cerebro.broker.setcommission(commission=0.0002)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe", timeframe=bt.TimeFrame.Minutes)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="dd")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="ta")
    cerebro.addanalyzer(TradeList,                  _name="tl")

    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(HmaSwitcher,
                        symbol=symbol,
                        pcts=PCTS[symbol],
                        lookup=LOOKUP[symbol],
                        eval_start=pd.to_datetime(START),
                        printlog=False)

    strat = cerebro.run()[0]

    # metrics
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd     = strat.analyzers.dd.get_analysis().max.drawdown
    ta     = strat.analyzers.ta.get_analysis()
    won    = ta.get("won",   {}).get("total", 0)
    lost   = ta.get("lost",  {}).get("total", 0)
    tot    = ta.get("total", {}).get("closed", 0)
    winr   = (won / tot * 100) if tot else 0.0

    avg_w  = ta.get("won",  {}).get("pnl", {}).get("average", 0.0)
    avg_l  = ta.get("lost", {}).get("pnl", {}).get("average", 0.0)
    expc   = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("nan")

    # R_mean
    trs = strat.analyzers.tl.get_analysis()
    r_vals = []
    for r in trs:
        risk = r.get("atr_entry", 0) * abs(r.get("size", 0))
        if risk:
            r_vals.append(r["pnl_comm"] / risk)
    r_mean = sum(r_vals)/len(r_vals) if r_vals else 0.0

    print(f"\n--- {symbol} SWITCH ({START}  {END}) ---")
    print(f"Sharpe: {sharpe:.2f}, DD: {dd:.2f}%, Trades: {tot}, Win%: {winr:.1f}%, Exp: {expc:.2f}, R_mean: {r_mean:.4f}")

    summary_rows.append({
        "symbol":     symbol,
        "period":     f"{START}{END}",
        "trades":     tot,
        "win_rate":   winr,
        "expectancy": expc,
        "sharpe":     sharpe,
        "drawdown":   dd,
        "R_mean":     r_mean,
    })

    for row in trs:
        row.update({"symbol": symbol, "period": f"{START}{END}"})
        trade_rows.append(row)


if __name__ == "__main__":
    for sym in SYMBOLS:
        run_symbol(sym)

    # write CSVs
    sum_path = RESULTS / "switch_summary.csv"
    trd_path = RESULTS / "switch_trades.csv"

    pd.DataFrame(summary_rows).to_csv(sum_path, index=False)

    # ensure tradeid
    for i, r in enumerate(trade_rows, 1):
        r["tradeid"] = i

    # minimal cols (extend if needed)
    cols = [
        "tradeid","dt_in","dt_out","price_in","price_out","size","side",
        "pnl","pnl_comm","barlen","atr_entry",
        "symbol","period"
    ]
    pd.DataFrame(trade_rows)[cols].to_csv(trd_path, index=False)

    print(f"\nWrote {sum_path}")
    print(f"Wrote {trd_path}")
