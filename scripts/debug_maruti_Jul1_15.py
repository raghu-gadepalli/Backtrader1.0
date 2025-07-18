#!/usr/bin/env python3
"""
Debug SuperTrend for MARUTI over July 1–15, 2025 with period=20, mult=3.
Hard‑coded for quick inspection.
"""

import os
import sys
import pandas as pd
import backtrader as bt

# Ensure project root is on PYTHONPATH
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles import load_candles
from strategies.supertrend import SuperTrend as STIndicator

def compute_supertrend(df, period, mult):
    # Normalize index → datetime column
    df2 = df.copy()
    if df2.index.name:
        df2 = df2.reset_index().rename(columns={df2.index.name: "datetime"})
    df2["datetime"] = pd.to_datetime(df2["datetime"])

    # Build Backtrader feed
    feed = bt.feeds.PandasData(
        dataname=df2,
        datetime="datetime",
        open="open", high="high", low="low",
        close="close", volume="volume",
        openinterest=None,
    )

    # Dummy strategy to attach SuperTrend
    class S(bt.Strategy):
        def __init__(self):
            self.st = STIndicator(self.data, period=period, multiplier=mult)

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(S)
    cerebro.adddata(feed)
    strat = cerebro.run()[0]

    # Record whether in uptrend each bar
    up = []
    for i in range(len(df2)):
        try:
            stv = float(strat.st.lines.st[i])
            up.append(df2.loc[i, "close"] > stv)
        except Exception:
            up.append(False)
    return pd.Series(up, name="in_uptrend", index=df2["datetime"])

def main():
    # — Hard‑coded settings for Jul 1–15, 2025 —
    symbol = "MARUTI"
    period = 20
    mult   = 3.0
    start  = "2025-07-01"
    end    = "2025-07-15"
    # ——————————————————————————————

    # 1) Load data
    df = load_candles(symbol, start, end)
    print(f"[INFO] Loaded {len(df)} bars for {symbol} [{start} → {end}]")

    # 2) Compute SuperTrend up/down series
    up = compute_supertrend(df, period, mult)
    print(f"[INFO] Computed SuperTrend (period={period}, mult={mult})")

    # 3) Count crossovers (trend shifts)
    shifts = int(up.astype(int).diff().abs().sum())
    trades = shifts // 2
    win_rate = round(up.mean() * 100, 2)
    print(f"[INFO] July 1–15: {trades} trades detected, win‑rate ≈ {win_rate}%\n")

    # 4) Show last few values for inspection
    combined = pd.DataFrame({
        "close": df["close"].values,
        "in_uptrend": up.values
    }, index=up.index)
    print(combined.tail(10))

if __name__ == "__main__":
    main()
