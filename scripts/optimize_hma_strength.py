#!/usr/bin/env python3
# scripts/optimize_hma_strength.py

import os
import sys
from datetime import datetime
import backtrader as bt

# ─── PROJECT ROOT ON PATH ──────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles                   import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

def optimize(symbol: str, start: str, end: str):
    cerebro = bt.Cerebro(stdstats=False)

    # 1) Performance analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # 2) Load data
    df = load_candles(symbol, start, end)
    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=1
    )
    cerebro.adddata(data)

    # 3) Opt-strategy: tune fast/mid1/mid2/mid3 (you can adjust these ranges)
    cerebro.optstrategy(
        HmaStateStrengthStrategy,
        fast=range(200, 801, 200),
        mid1=range(400, 1401, 400),
        mid2=range(800, 2001, 600),
        mid3=range(1200, 3801, 800),
        atr_mult=[0.0, 0.1, 0.2]
    )

    # 4) Remember starting value
    start_value = cerebro.broker.getvalue()

    # 5) Run in parallel
    opt_runs = cerebro.run(maxcpus=4)

    # 6) Collect results
    results = []
    for run in opt_runs:
        # run may be an OptReturn (iterable), or a list/tuple of Strategy instances
        strat = run[0] if isinstance(run, (list, tuple)) else run
        p     = strat.p
        val   = strat.broker.getvalue()
        pnl   = round(val - start_value, 2)
        sa    = strat.analyzers.sharpe.get_analysis()
        sharpe = sa.get("sharperatio", None)
        dd    = strat.analyzers.drawdown .get_analysis().max.drawdown
        tr    = strat.analyzers.trades   .get_analysis()
        won   = tr.get("won",   {}).get("total", 0)
        lost  = tr.get("lost",  {}).get("total", 0)
        tot   = tr.get("total",{}).get("closed",0)

        results.append({
            "fast":     p.fast,
            "mid1":     p.mid1,
            "mid2":     p.mid2,
            "mid3":     p.mid3,
            "atr_mult": p.atr_mult,
            "PnL":      pnl,
            "Sharpe":   round(sharpe, 3) if sharpe is not None else None,
            "MaxDD%":   round(dd, 2),
            "Trades":   f"{won}W/{lost}L ({tot})"
        })

    # 7) Sort & display top 10 by PnL
    results.sort(key=lambda x: x["PnL"], reverse=True)
    print(f"\nTop 10 HMA‐strength parameter sets for {symbol} ({start}→{end}):\n")
    for r in results[:10]:
        print((
            f" fast={r['fast']:>4} mid1={r['mid1']:>5} "
            f"mid2={r['mid2']:>5} mid3={r['mid3']:>6}  "
            f"ATR×{r['atr_mult']:>4} → "
            f"PnL={r['PnL']:>7}  Sharpe={r['Sharpe']:>5}  "
            f"MaxDD%={r['MaxDD%']:>5}  Trades={r['Trades']}"
        ))
    print()

if __name__ == "__main__":
    # you can swap out INFY for ICICIBANK, RELIANCE, etc.
    optimize(
        symbol="INFY",
        start="2025-04-01",
        end="2025-07-06"
    )
