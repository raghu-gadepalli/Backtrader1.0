#!/usr/bin/env python3
import os, sys
from datetime import datetime

# headless plotting
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

# --- ensure project root on path ---
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles       import load_candles
from strategies.MacdStrategy import MacdStrategy  # adjust if your class is named differently

# -----------------------------------------------------------------------------
# USER CONFIGURATION
SYMBOL   = "INFY"
MACD1    = 120    # fast EMA period
MACD2    = 240   # slow EMA period
SIG      = 60    # signal-line EMA period

WARMUP_START = "2025-04-01"
TRAIN_START  = "2025-05-01"
TRAIN_END    = "2025-05-31"
TEST_START   = "2025-06-01"
TEST_END     = "2025-06-30"
# -----------------------------------------------------------------------------

def run_period(symbol, start, end, macd1, macd2, signal):
    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    # load warmup + period data
    df = load_candles(symbol, WARMUP_START, end)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(MacdStrategy,
                        macd1  = macd1,
                        macd2  = macd2,
                        signal = signal,
                        printlog=False)

    strat = cerebro.run()[0]

    sr  = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd  = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr  = strat.analyzers.trades.get_analysis()
    won = tr.get("won",  {}).get("total", 0)
    lst = tr.get("lost", {}).get("total", 0)
    tot = tr.get("total",{}).get("closed", 0)
    wr  = (won/tot*100) if tot else 0.0

    print(f"\n--- {symbol} | {start} → {end} @ MACD({macd1},{macd2},{signal}) ---")
    print(f"Sharpe Ratio : {sr:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {wr:.1f}% ({won}W/{lst}L)")

if __name__ == "__main__":
    # training
    run_period(SYMBOL, TRAIN_START, TRAIN_END, MACD1, MACD2, SIG)
    # testing
    run_period(SYMBOL, TEST_START,  TEST_END,  MACD1, MACD2, SIG)
