#!/usr/bin/env python3
import os
import sys
import pandas as pd

# headless plotting
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

#  project root 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles import load_candles
from strategies.macd      import MacdStrategy

#  user configuration 
SYMBOLS    = ["AXISBANK","HDFCBANK","ICICIBANK","INFY","KOTAKBANK",
              "SBIN","SUNPHARMA","TECHM"]
MACD_PARAMS = dict(macd1=120, macd2=240, signal=60, printlog=False)

WARMUP     = "2025-04-01"
TRAIN      = ("2025-05-01", "2025-05-31")
TEST       = ("2025-06-01", "2025-06-30")

def run_period(symbol, start, end):
    df = load_candles(symbol, WARMUP, end)
    df.index = pd.to_datetime(df.index)

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(MacdStrategy, **MACD_PARAMS)

    strat = cerebro.run()[0]
    sharpe  = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd      = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr      = strat.analyzers.trades.get_analysis()
    won     = tr.get("won",  {}).get("total", 0)
    lost    = tr.get("lost", {}).get("total", 0)
    tot     = tr.get("total",{}).get("closed", 0)
    winrate = (won/tot*100) if tot else 0.0

    print(f"\n--- {symbol} | {start}  {end} @ MACD"
          f"({MACD_PARAMS['macd1']},"
          f"{MACD_PARAMS['macd2']},"
          f"{MACD_PARAMS['signal']}) ---")
    print(f"Sharpe Ratio : {sharpe:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {winrate:.1f}% ({won}W/{lost}L)")

if __name__ == "__main__":
    for sym in SYMBOLS:
        run_period(sym, *TRAIN)
        run_period(sym, *TEST)
