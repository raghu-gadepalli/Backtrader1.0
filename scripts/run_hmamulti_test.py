#!/usr/bin/env python3
# scripts/run_hmamulti_test.py

import os
import sys
import pandas as pd

# headless plotting
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

# ─── project root ───────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles        import load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy  # :contentReference[oaicite:0]{index=0}

# ─── per‐symbol multi‑HMA parameters ────────────────────────────────────────────
HMA_MULTI_PARAMS = {
    "AXISBANK":  dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
    "HDFCBANK":  dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
    "ICICIBANK": dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
    "INFY":      dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
    "KOTAKBANK": dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
    "MARUTI":    dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
    "SBIN":      dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
    "SUNPHARMA": dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
    "TATAMOTORS":dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
    "TCS":       dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
    "TECHM":     dict(fast=600, mid1=760, mid2=1040, mid3=1520,
                      atr_period=14, atr_mult=0.1, adx_period=14,
                      adx_threshold=25.0, printlog=False),
}

SYMBOLS     = list(HMA_MULTI_PARAMS.keys())
WARMUP      = "2025-04-01"
TRAIN_START = "2025-05-01"
TRAIN_END   = "2025-05-31"
TEST_START  = "2025-06-01"
TEST_END    = "2025-06-30"
JULY_START  = "2025-07-01"
JULY_END    = "2025-07-14"  # first 14 days

def run_period(symbol, start, end, params):
    # load warmup + backtest data
    df = load_candles(symbol, WARMUP, end)
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

    cerebro.addstrategy(HmaMultiTrendStrategy, **params)

    strat = cerebro.run()[0]
    sr    = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd    = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr    = strat.analyzers.trades.get_analysis()
    won   = tr.get("won",  {}).get("total", 0)
    lost  = tr.get("lost", {}).get("total", 0)
    tot   = tr.get("total",{}).get("closed", 0)
    wr    = (won / tot * 100) if tot else 0.0

    p = params
    print(f"\n--- {symbol} | {start} → {end} @ HMA_MULTI"
          f"({p['fast']},{p['mid1']},{p['mid2']},{p['mid3']},"
          f"atr{p['atr_period']}/{p['atr_mult']},"
          f"adx{p['adx_period']}/{p['adx_threshold']}) ---")
    print(f"Sharpe Ratio : {sr:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {wr:.1f}% ({won}W/{lost}L)")

if __name__ == "__main__":
    for symbol, params in HMA_MULTI_PARAMS.items():
        # May
        run_period(symbol, TRAIN_START, TRAIN_END, params)
        # June
        run_period(symbol, TEST_START,  TEST_END,  params)
        # July 1–14
        run_period(symbol, JULY_START, JULY_END,  params)
