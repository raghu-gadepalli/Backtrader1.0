#!/usr/bin/env python3
# scripts/run_supertrend_test.py

import os
import sys
import argparse
import pandas as pd

# headless Matplotlib
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

# ─── project root ───────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles import load_candles

# ─── SuperTrend indicator ──────────────────────────────────────────────────────
class SuperTrend(bt.Indicator):
    lines = ("st",)
    params = dict(period=120, multiplier=3.0)

    def __init__(self):
        atr = bt.ind.ATR(self.data, period=self.p.period)
        hl2 = (self.data.high + self.data.low) / 2
        upper = hl2 + self.p.multiplier * atr
        lower = hl2 - self.p.multiplier * atr

        # recursive ST line: stays within the last band until flip
        self.l.st = bt.If(
            self.data.close > self.l.st(-1),
            bt.Min(upper, self.l.st(-1)),
            bt.Max(lower, self.l.st(-1)),
        )

# ─── strategy using only SuperTrend ────────────────────────────────────────────
class STOnlyStrategy(bt.Strategy):
    params = dict(st_period=120, st_mult=3.0)

    def __init__(self):
        self.st = SuperTrend(self.data,
                             period=self.p.st_period,
                             multiplier=self.p.st_mult)

    def next(self):
        price = self.data.close[0]
        if price > self.st[0] and not self.position:
            self.buy()
        elif price < self.st[0] and self.position:
            self.close()

# ─── your symbol list ──────────────────────────────────────────────────────────
SYMBOLS = [
    "AXISBANK", "HDFCBANK", "ICICIBANK", "INFY", "KOTAKBANK", "MARUTI",
    "NIFTY 50", "NIFTY BANK", "RELIANCE", "SBIN", "SUNPHARMA",
    "TATAMOTORS", "TCS", "TECHM"
]

WARMUP      = "2025-04-01"
TRAIN_START = "2025-05-01"
TRAIN_END   = "2025-05-31"
TEST_START  = "2025-06-01"
TEST_END    = "2025-06-30"

def run_period(symbol, start, end, st_period, st_mult):
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

    cerebro.addstrategy(STOnlyStrategy,
                        st_period=st_period,
                        st_mult=  st_mult)

    strat = cerebro.run()[0]
    sa = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr = strat.analyzers.trades.get_analysis()
    won  = tr.get("won", {}).get("total", 0)
    lost = tr.get("lost", {}).get("total", 0)
    total = tr.get("total", {}).get("closed", 0)
    winr  = (won/total*100) if total else 0.0

    print(f"\n--- {symbol} | {start}→{end} @ ST({st_period},{st_mult}) ---")
    print(f"Sharpe Ratio : {sa:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winr:.1f}% ({won}W/{lost}L)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SuperTrend-only backtest")
    parser.add_argument("--st-period", type=int,   default=120,
                        help="ATR period for SuperTrend (default: 120)")
    parser.add_argument("--st-mult",   type=float, default=3.0,
                        help="ATR multiplier for SuperTrend (default: 3.0)")
    args = parser.parse_args()

    for sym in SYMBOLS:
        run_period(sym, TRAIN_START, TRAIN_END,
                   st_period=args.st_period,
                   st_mult=  args.st_mult)
        run_period(sym, TEST_START,  TEST_END,
                   st_period=args.st_period,
                   st_mult=  args.st_mult)
