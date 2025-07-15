#!/usr/bin/env python3
import os
import sys
from datetime import datetime

#  headless plotting 
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import pandas as pd
import backtrader as bt

#  project root 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles          import load_candles
from strategies.hma_crossover   import HmaCrossoverStrategy  # :contentReference[oaicite:0]{index=0}

#  USER CONFIGURATION 
SYMBOL        = "INFY"
FAST, SLOW    = 200, 300      # HMA periods
ATR_PERIOD    = 14            # ATR length for noisefiltering
ATR_MULT      = 1.0           # require gap > ATRATR_MULT

WARMUP_START  = "2025-04-01"
TRAIN_START   = "2025-05-01"
TRAIN_END     = "2025-05-31"
TEST_START    = "2025-06-01"
TEST_END      = "2025-06-30"
# 

def run_period(symbol, start, end, fast, slow, atr_period, atr_mult):
    # 1) load warmup + full window
    df = load_candles(symbol, WARMUP_START, end)
    df.index = pd.to_datetime(df.index)
    # 2) trim to exact train/test window
    df = df.loc[start:end]

    # 3) set up Cerebro
    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    # 4) wire in your HMAcrossover strategy
    cerebro.addstrategy(HmaCrossoverStrategy,
                        fast       = fast,
                        slow       = slow,
                        atr_period = atr_period,
                        atr_mult   = atr_mult,
                        printlog   = False)

    # 5) run & grab metrics
    strat = cerebro.run()[0]
    sr    = strat.analyzers.sharpe .get_analysis().get("sharperatio", 0.0) or 0.0
    dd    = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr    = strat.analyzers.trades.get_analysis()
    won   = tr.get("won",  {}).get("total", 0)
    lost  = tr.get("lost", {}).get("total", 0)
    tot   = tr.get("total",{}).get("closed", 0)
    wr    = (won/tot*100) if tot else 0.0

    # 6) print summary
    print(f"\n--- {symbol} | {start}  {end} @ HMAXOVER({fast},{slow},ATR{atr_period}{atr_mult}) ---")
    print(f"Sharpe Ratio : {sr:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {wr:.1f}% ({won}W/{lost}L)")

if __name__ == "__main__":
    # training period
    run_period(SYMBOL, TRAIN_START, TRAIN_END,
               FAST, SLOW, ATR_PERIOD, ATR_MULT)
    # testing period
    run_period(SYMBOL, TEST_START,  TEST_END,
               FAST, SLOW, ATR_PERIOD, ATR_MULT)
