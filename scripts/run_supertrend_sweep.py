#!/usr/bin/env python3
# scripts/run_supertrend_sweep.py

import os
import sys
import csv
import pandas as pd

# force headless plotting
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
    params = dict(period=60, multiplier=3.0)

    def __init__(self):
        atr = bt.ind.ATR(self.data, period=self.p.period)
        hl2 = (self.data.high + self.data.low) / 2
        upper = hl2 + self.p.multiplier * atr
        lower = hl2 - self.p.multiplier * atr

        # recursive ST line: stays within last band until price flips
        self.l.st = bt.If(
            self.data.close > self.l.st(-1),
            bt.Min(upper, self.l.st(-1)),
            bt.Max(lower, self.l.st(-1)),
        )

# ─── simple strategy using only SuperTrend ─────────────────────────────────────
class STOnlyStrategy(bt.Strategy):
    params = dict(st_period=60, st_mult=2.0)

    def __init__(self):
        self.st = SuperTrend(self.data,
                             period=self.p.st_period,
                             multiplier=self.p.st_mult)

    def next(self):
        if not self.position and self.data.close[0] > self.st[0]:
            self.buy()
        elif self.position and self.data.close[0] < self.st[0]:
            self.close()

# ─── configuration ─────────────────────────────────────────────────────────────
SYMBOLS = [
    "AXISBANK","HDFCBANK","ICICIBANK","INFY","KOTAKBANK","MARUTI",
    "NIFTY 50","NIFTY BANK","RELIANCE","SBIN","SUNPHARMA",
    "TATAMOTORS","TCS","TECHM"
]
WARMUP      = "2025-04-01"
TRAIN_START = "2025-05-01"
TRAIN_END   = "2025-05-31"
TEST_START  = "2025-06-01"
TEST_END    = "2025-06-30"

# PERIODS = [30, 40, 60, 80, 120, 160, 180, 240]
PERIODS = [20]
MULTS   = [1.8, 2.0, 2.2, 2.5, 3.0]

OUT_DIR = os.path.join(_ROOT, "results")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_CSV = os.path.join(OUT_DIR, "supertrend_sweep.csv")

# ─── backtest & metric extraction ───────────────────────────────────────────────
def run_bt(symbol, start, end, per, mult):
    # load and resample
    df = load_candles(symbol, WARMUP, end)
    df.index = pd.to_datetime(df.index)

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes,
                        riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(STOnlyStrategy,
                        st_period=per,
                        st_mult=  mult)

    strat = cerebro.run()[0]

    # metrics
    sa = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr = strat.analyzers.trades.get_analysis()
    won  = tr.get("won", {}).get("total", 0)
    lost = tr.get("lost", {}).get("total", 0)
    total = won + lost
    winr = (won/total*100) if total else 0.0

    return {
        "symbol":    symbol,
        "phase":     "train" if start==TRAIN_START else "test",
        "start":     start,
        "end":       end,
        "period":    per,
        "mult":      mult,
        "sharpe":    round(sa, 4),
        "max_dd":    round(dd, 4),
        "trades":    total,
        "win_rate":  round(winr, 2),
        "won":       won,
        "lost":      lost
    }

# ─── main sweep ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # open CSV and write header
    with open(OUT_CSV, "w", newline="") as f:
        cols = ["symbol","phase","start","end",
                "period","mult","sharpe","max_dd",
                "trades","win_rate","won","lost"]
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()

        # loop through all combinations
        for per in PERIODS:
            for mult in MULTS:
                for sym in SYMBOLS:
                    for (start,end) in [(TRAIN_START,TRAIN_END),
                                        (TEST_START, TEST_END)]:
                        out = run_bt(sym, start, end, per, mult)
                        # print to console
                        print(f"{out['symbol']:10s} | {out['start']}→{out['end']} "
                              f"@ ST({per},{mult:.1f}) → "
                              f"Sharpe={out['sharpe']:.2f}, DD={out['max_dd']:.2f}%, "
                              f"Trades={out['trades']}, Win={out['win_rate']:.1f}%")
                        # write row
                        writer.writerow(out)

    print(f"\n✔ All results written to {OUT_CSV}\n")
