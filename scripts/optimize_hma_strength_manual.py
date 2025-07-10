#!/usr/bin/env python3
# scripts/optimize_hma_strength_manual.py

import os, sys, csv
from itertools import product
from datetime import datetime

import backtrader as bt

# ─── PROJECT ROOT ON PATH ──────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles                   import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

def optimize_manual(symbol, start, end):
    # 1) parameter grid (shrink these if it’s still too slow)
    fasts    = [200, 400, 600, 800]
    mids1    = [400, 800, 1200]
    mids2    = [800, 1400, 2000]
    mids3    = [1200, 2400, 3600]
    atr_mult = [0.0, 0.1, 0.2]

    combos = list(product(fasts, mids1, mids2, mids3, atr_mult))
    total  = len(combos)

    # 2) prepare output file
    results_file = os.path.join(_ROOT, "results", f"{symbol}_hma_strength_opt.csv")
    os.makedirs(os.path.dirname(results_file), exist_ok=True)
    with open(results_file, "w", newline="") as fo:
        writer = csv.writer(fo)
        writer.writerow([
            "fast","mid1","mid2","mid3","atr_mult",
            "PnL","Sharpe","MaxDD%","TotalTrades","WinRate%"
        ])

        # 3) run each combo one by one
        for idx, (f, m1, m2, m3, am) in enumerate(combos, 1):
            print(f"[{idx}/{total}] fast={f} mid1={m1} mid2={m2} mid3={m3} atr×{am}")
            cerebro = bt.Cerebro(stdstats=False)
            # analyzers
            cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                                timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
            cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")
            # data
            df = load_candles(symbol, start, end)
            data = bt.feeds.PandasData(dataname=df,
                                       timeframe=bt.TimeFrame.Minutes,
                                       compression=1)
            cerebro.adddata(data)
            # strategy
            cerebro.addstrategy(
                HmaStateStrengthStrategy,
                fast=f, mid1=m1, mid2=m2, mid3=m3,
                atr_mult=am, printlog=False
            )
            # run
            strat = cerebro.run()[0]

            # metrics
            start_cash = cerebro.broker.startingcash
            end_val    = strat.broker.getvalue()
            pnl        = round(end_val - start_cash, 2)
            sharpe     = strat.analyzers.sharpe.get_analysis().get("sharperatio", None)
            dd         = strat.analyzers.drawdown.get_analysis().max.drawdown
            ta         = strat.analyzers.trades.get_analysis()
            won        = ta.get("won",{}).get("total",0)
            lost       = ta.get("lost",{}).get("total",0)
            tot        = ta.get("total",{}).get("closed",0)
            winrate    = round(won/ tot*100, 1) if tot else 0.0

            # write row
            writer.writerow([
                f, m1, m2, m3, am,
                pnl,
                round(sharpe,3) if sharpe is not None else "",
                round(dd,2),
                tot,
                winrate
            ])
            fo.flush()

    print(f"\nDone! Results written to {results_file}")

if __name__ == "__main__":
    optimize_manual(
        symbol="INFY",
        start ="2025-04-01",
        end   ="2025-07-06"
    )
