#!/usr/bin/env python3
# scripts/run_hma_final.py

import os, sys
from pathlib import Path
# force headless
os.environ["MPLBACKEND"] = "Agg"
import backtrader as bt
import pandas as pd

# project root on path
_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_ROOT))

from data.load_candles                   import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

# Final, locked-in HMA params per symbol
PARAMS = {
    "ICICIBANK": dict(fast=180, mid1= 540, mid2= 900, mid3=1440, atr_mult=0.0),
    "INFY":      dict(fast= 60, mid1= 120, mid2= 240, mid3=1680, atr_mult=0.0),
    "RELIANCE":  dict(fast= 60, mid1= 180, mid2= 240, mid3=1680, atr_mult=0.0),
}

WARMUP = "2025-04-01"
PERIODS = [
    ("2025-05-01", "2025-05-31", "MAY"),
    ("2025-06-01", "2025-06-30", "JUN"),
]

def run_period(sym, start, end, p):
    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    df = load_candles(sym, WARMUP, end)
    data = bt.feeds.PandasData(dataname=df, timeframe=bt.TimeFrame.Minutes)
    cerebro.adddata(data, name=sym)

    cerebro.addstrategy(HmaStateStrengthStrategy,
                        fast     = p["fast"],
                        mid1     = p["mid1"],
                        mid2     = p["mid2"],
                        mid3     = p["mid3"],
                        atr_mult = p["atr_mult"],
                        printlog = False)

    strat = cerebro.run()[0]
    sr   = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd   = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr   = strat.analyzers.trades.get_analysis()
    total= tr.get("total", {}).get("closed", 0)
    won  = tr.get("won",   {}).get("total",  0)
    lost = tr.get("lost",  {}).get("total",  0)
    wr   = won/total*100 if total else 0.0

    return {
        "symbol":   sym,
        "period":   f"{start}→{end}",
        "fast":     p["fast"],
        "sharpe":   round(sr, 4),
        "drawdown": round(dd, 2),
        "trades":   total,
        "win_rate": round(wr, 1),
        "wins":     won,
        "losses":   lost
    }

def main():
    rows = []
    print("Running final backtests with locked-in HMA params:\n")
    for sym, p in PARAMS.items():
        print(f"=== {sym} (fast={p['fast']}, mids={p['mid1']},{p['mid2']},{p['mid3']}) ===")
        for start, end, label in PERIODS:
            print(f" → {label}: {start}→{end} ...", end=" ")
            r = run_period(sym, start, end, p)
            print(f"Sharpe={r['sharpe']}, Trades={r['trades']}, Win={r['win_rate']}%")
            rows.append(r)

    df = pd.DataFrame(rows)
    out = Path("hma_final_results.xlsx")
    df.to_excel(out, index=False)
    print(f"\nDone! Detailed results in {out}")

if __name__ == "__main__":
    main()
