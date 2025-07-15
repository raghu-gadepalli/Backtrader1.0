#!/usr/bin/env python3
# scripts/run_supertrend_sweep_restricted.py

import os, sys, pandas as pd
os.environ["MPLBACKEND"]="Agg"
import matplotlib; matplotlib.use("Agg", force=True)
import backtrader as bt

# ─── project root ───────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path: sys.path.insert(0, _ROOT)
from data.load_candles import load_candles

# ─── SuperTrend indicator ──────────────────────────────────────────────────────
class SuperTrend(bt.Indicator):
    lines = ("st",)
    params = dict(period=60, multiplier=3.0)
    def __init__(self):
        atr = bt.ind.ATR(self.data, period=self.p.period)
        hl2 = (self.data.high + self.data.low)/2
        upper = hl2 + self.p.multiplier*atr
        lower = hl2 - self.p.multiplier*atr
        self.l.st = bt.If(
            self.data.close > self.l.st(-1),
            bt.Min(upper, self.l.st(-1)),
            bt.Max(lower, self.l.st(-1)),
        )

class STOnly(bt.Strategy):
    params = dict(st_period=60, st_mult=2.0)
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

SYMS    = ["AXISBANK","HDFCBANK","ICICIBANK","INFY","KOTAKBANK","MARUTI",
           "NIFTY 50","NIFTY BANK","RELIANCE","SBIN","SUNPHARMA",
           "TATAMOTORS","TCS","TECHM"]
WARMUP  = "2025-04-01"
TR_S,TR_E="2025-05-01","2025-05-31"
TE_S,TE_E="2025-06-01","2025-06-30"

# our restricted grid
PERIODS = [30,40,60,80,120,160,180,240]
MULTS   = [1.8,2.0,2.2,2.5,3.0]

def run_bt(sym, start, end, per, mult):
    df = load_candles(sym, WARMUP, end)
    df.index = pd.to_datetime(df.index)
    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=sym)
    cerebro.addstrategy(STOnly, st_period=per, st_mult=mult)
    strat = cerebro.run()[0]
    s  = strat.analyzers.sharpe.get_analysis().get("sharperatio") or 0
    dd = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr = strat.analyzers.trades.get_analysis()
    w  = tr.get("won",{}).get("total",0)
    l  = tr.get("lost",{}).get("total",0)
    tot= w+l
    wr = w/tot*100 if tot else 0
    print(f"{sym:10s} | {start}→{end} | ST({per},{mult:.1f}) "
          f"Sharpe {s:.2f}, DD {dd:.2f}%, Trades {tot}, Win {wr:.1f}%")

if __name__=="__main__":
    for per in PERIODS:
        for mult in MULTS:
            for sym in SYMS:
                run_bt(sym, TR_S, TR_E, per, mult)
                run_bt(sym, TE_S, TE_E, per, mult)
