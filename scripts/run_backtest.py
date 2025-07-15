#!/usr/bin/env python3
# scripts/run_backtest.py

import os, sys
import pandas as pd

# headless Matplotlib
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

#  project root 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles     import load_candles
from strategies.supertrend import SuperTrend, ST

#  persymbol SuperTrend settings 
ST_PARAMS = {
    "AXISBANK":  dict(period=60,  mult=2.0),
    "HDFCBANK":  dict(period=120, mult=1.8),
    "ICICIBANK": dict(period=120, mult=1.8),
    "INFY":      dict(period=60,  mult=2.0),
    "KOTAKBANK": dict(period=80,  mult=2.0),
    "SBIN":      dict(period=120, mult=1.8),
    "SUNPHARMA": dict(period=80,  mult=1.8),
    "TECHM":     dict(period=120, mult=1.8),
}

#  warmup & test windows 
WARMUP_START = "2025-01-01"   # load from Jan1 to let ST settle
TEST_START   = "2025-02-01"   # reporting begins Feb1
TEST_END     = "2025-02-28"   # through Feb28

def run_backtest(symbol, warmup, test_start, test_end, st_period, st_mult):
    # load full warmup + test data
    df = load_candles(symbol, warmup, test_end)
    df.index = pd.to_datetime(df.index)

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(ST,
                        st_period=st_period,
                        st_mult=  st_mult)

    strat = cerebro.run()[0]

    # pull raw stats
    sharpe  = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd      = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr      = strat.analyzers.trades.get_analysis()
    won     = tr.get("won",  {}).get("total", 0)
    lost    = tr.get("lost", {}).get("total", 0)
    total   = tr.get("total",{}).get("closed", 0)
    winrate = (won/total*100) if total else 0.0

    # report only the test window
    print(f"\n--- {symbol} | {test_start}  {test_end} @ ST({st_period},{st_mult}) ---")
    print(f"Sharpe Ratio : {sharpe:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winrate:.1f}% ({won}W/{lost}L)")

if __name__ == "__main__":
    for symbol, params in ST_PARAMS.items():
        run_backtest(
            symbol,
            WARMUP_START,
            TEST_START,
            TEST_END,
            st_period=params["period"],
            st_mult=  params["mult"]
        )
