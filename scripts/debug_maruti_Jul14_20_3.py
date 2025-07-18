#!/usr/bin/env python3
"""
Debug SuperTrend for MARUTI on July 14, 2025 (09:00–15:30),
seeding the 20‑bar ATR with July 13 data.
"""

import os, sys, pandas as pd, backtrader as bt

# ─── add your project root to PYTHONPATH ─────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ─────────────────────────────────────────────────────────────────────────────

from data.load_candles import load_candles
from strategies.supertrend import SuperTrend as STIndicator

def compute_supertrend_debug(df, period, mult):
    # normalize index → datetime column
    df2 = df.copy()
    if df2.index.name:
        df2 = df2.reset_index().rename(columns={df2.index.name: "datetime"})
    df2["datetime"] = pd.to_datetime(df2["datetime"])

    feed = bt.feeds.PandasData(
        dataname     = df2,
        datetime     = "datetime",
        open         = "open",
        high         = "high",
        low          = "low",
        close        = "close",
        volume       = "volume",
        openinterest = None,
    )

    class DebugStrat(bt.Strategy):
        def __init__(self):
            self.st    = STIndicator(self.data, period=period, multiplier=mult)
            self.dates  = []
            self.closes = []
            self.stv    = []
            self.tr     = []

        def next(self):
            dt    = self.data.datetime.datetime(0)
            price = float(self.data.close[0])
            val   = float(self.st[0])
            self.dates.append(dt)
            self.closes.append(price)
            self.stv.append(val)
            self.tr.append(price > val)

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(DebugStrat)
    cerebro.adddata(feed)
    strat = cerebro.run()[0]

    return pd.DataFrame({
        "datetime":    strat.dates,
        "close":       strat.closes,
        "supertrend":  strat.stv,
        "in_uptrend":  strat.tr,
    }).set_index("datetime")

def main():
    symbol = "MARUTI"
    period = 20
    mult   = 3.0

    # Load Jul 13 (for warm‑up) through Jul 14 15:30
    df = load_candles(
        symbol,
        "2025-07-13 14:00:00",   # seed start (enough bars before open)
        "2025-07-14 15:30:00"
    )
    if df.empty:
        print("[ERROR] No bars loaded—check your datetimes!")
        return
    print(f"[INFO] Loaded {len(df)} bars from 2025‑07‑13 14:00 → 2025‑07‑14 15:30\n")

    st_df = compute_supertrend_debug(df, period, mult)
    print(f"[INFO] Computed SuperTrend (period={period}, mult={mult})\n")

    # Now focus on Jul 14 09:00–15:30
    window = st_df.loc["2025-07-14 09:00":"2025-07-14 15:30"]
    shifts = int(window["in_uptrend"].astype(int).diff().abs().sum())
    trades = shifts // 2
    win_rate = round(window["in_uptrend"].mean() * 100, 2)
    print(f"[INFO] July 14 (seeded): Trades={trades}, Win Rate={win_rate}%\n")

    # Print each flip
    flips = window[window["in_uptrend"].astype(int).diff().abs() == 1]
    print("=== FLIPS on 2025‑07‑14 (09:00–15:30) ===\n")
    print(flips[["close","supertrend","in_uptrend"]].to_string())

if __name__ == "__main__":
    main()
