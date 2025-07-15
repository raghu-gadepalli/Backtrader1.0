#!/usr/bin/env python3
# scripts/run_supertrend_sweep.py

import os
import sys
import backtrader as bt
import pandas as pd

# headless Matplotlib
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

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
        atr   = bt.ind.ATR(self.data, period=self.p.period)
        hl2   = (self.data.high + self.data.low) / 2
        upper = hl2 + self.p.multiplier * atr
        lower = hl2 - self.p.multiplier * atr

        self.l.st = bt.If(
            self.data.close > self.l.st(-1),
            bt.Min(upper, self.l.st(-1)),
            bt.Max(lower, self.l.st(-1)),
        )

# ─── SuperTrend‐only strategy ──────────────────────────────────────────────────
class ST(bt.Strategy):
    params = dict(st_period=120, st_mult=3.0)

    def __init__(self):
        self.st = SuperTrend(self.data,
                             period=self.p.st_period,
                             multiplier=self.p.st_mult)

    def next(self):
        price = self.data.close[0]
        if not self.position and price > self.st[0]:
            self.buy()
        elif self.position and price < self.st[0]:
            self.close()

# ─── symbols & parameter grid ─────────────────────────────────────────────────
SYMBOLS = [
    "AXISBANK", "HDFCBANK", "ICICIBANK", "INFY",
    "KOTAKBANK", "MARUTI", "RELIANCE", "SBIN",
    "SUNPHARMA", "TECHM"
]

PERIODS = [30, 40, 60, 80, 120, 160, 180, 240]
MULTS   = [1.8, 2.0, 2.2, 2.5, 3.0]

# ─── walk‑forward windows for tuning ───────────────────────────────────────────
WINDOWS = [
    {
        "label": "Jan→Feb",
        "warm":  "2025-01-01",
        "start": "2025-02-01",
        "end":   "2025-02-28",
    },
    {
        "label": "Feb→Mar",
        "warm":  "2025-02-01",
        "start": "2025-03-01",
        "end":   "2025-03-31",
    },
    {
        "label": "Mar→Apr",
        "warm":  "2025-03-01",
        "start": "2025-04-01",
        "end":   "2025-04-30",
    },
]

def run_sweep(symbol, warm, start, end, period, mult):
    # load warm‑up through end
    df = load_candles(symbol, warm, end)
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

    cerebro.addstrategy(
        ST,
        st_period=period,
        st_mult=mult
    )

    strat = cerebro.run()[0]
    sr    = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd    = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr    = strat.analyzers.trades.get_analysis()
    won   = tr.get("won",  {}).get("total", 0)
    lost  = tr.get("lost", {}).get("total",   0)
    tot   = tr.get("total",{}).get("closed",  0)
    wr    = (won / tot * 100) if tot else 0.0

    print(f"\n--- {symbol} | {WINDOWS_LABEL} @ ST({period},{mult}) "
          f"[warm‑up {warm} ▶ test {start}→{end}] ---")
    print(f"Sharpe Ratio : {sr:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {wr:.1f}% ({won}W/{lost}L)")

if __name__ == "__main__":
    for symbol in SYMBOLS:
        for period in PERIODS:
            for mult in MULTS:
                for w in WINDOWS:
                    # make WINDOWS_LABEL available inside run_sweep
                    WINDOWS_LABEL = w["label"]
                    run_sweep(
                        symbol,
                        warm   = w["warm"],
                        start  = w["start"],
                        end    = w["end"],
                        period = period,
                        mult   = mult
                    )
