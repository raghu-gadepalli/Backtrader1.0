#!/usr/bin/env python3
# scripts/run_backtest.py

import os
import sys
import pandas as pd

# headless Matplotlib
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

# ─── project root ───────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles     import load_candles
from strategies.supertrend import ST  # we import only the Strategy class

# ─── which symbols & ST settings you want to run ───────────────────────────────
ST_PARAMS = {
    "HDFCBANK": dict(period=120, mult=2.0),
    # add others here when you’re ready
}

# ─── warm‑up & test windows ────────────────────────────────────────────────────
WARMUP_START = "2025-01-01"  # used to “seed” the indicator
TEST_START   = "2025-02-01"  # only trades from here on are reported
TEST_END     = "2025-02-28"

def run_backtest(symbol, warmup_from, test_from, test_to, st_period, st_mult):
    # 1) load everything from warmup to end of test
    df = load_candles(symbol, warmup_from, test_to)
    df.index = pd.to_datetime(df.index)

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    # 2) feed the data
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    # 3) add _only_ the ST params to the strategy
    cerebro.addstrategy(ST,
                        st_period=st_period,
                        st_mult=  st_mult)

    # 4) run and grab stats
    strat = cerebro.run()[0]
    sr   = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd   = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr   = strat.analyzers.trades.get_analysis()
    won  = tr.get("won",  {}).get("total", 0)
    lost = tr.get("lost", {}).get("total", 0)
    tot  = tr.get("total",{}).get("closed", 0)
    wr   = (won/tot*100) if tot else 0.0

    # 5) print only the test‐window results
    print(f"\n--- {symbol} | {test_from} → {test_to} @ ST({st_period},{st_mult}) ---")
    print(f"Sharpe Ratio : {sr:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {wr:.1f}% ({won}W/{lost}L)")

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
