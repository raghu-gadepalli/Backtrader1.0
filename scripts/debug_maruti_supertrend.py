#!/usr/bin/env python3
"""
Mini‑sweep of SuperTrend on MARUTI over Jan–Jun 2025.
Prints out number of trades and win‑rate for each (period, mult) combo.
"""

import os, sys
import pandas as pd
import backtrader as bt

# ---- Adjust this path if your project root differs ----
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles import load_candles
from strategies.supertrend import SuperTrend as STIndicator

def compute_supertrend(df, period, mult):
    """Return DataFrame with a boolean 'in_uptrend' column."""
    # normalize index→datetime column
    df2 = df.copy()
    if df2.index.name:
        df2 = df2.reset_index().rename(columns={df2.index.name: "datetime"})
    df2["datetime"] = pd.to_datetime(df2["datetime"])

    # backtrader feed
    feed = bt.feeds.PandasData(
        dataname=df2,
        datetime="datetime",
        open="open", high="high", low="low",
        close="close", volume="volume",
        openinterest=None,
    )
    # dummy strategy to attach indicator
    class S( bt.Strategy ):
        def __init__(self):
            self.st = STIndicator(self.data, period=period, multiplier=mult)

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(S)
    cerebro.adddata(feed)
    strat = cerebro.run()[0]

    # collect results
    up = []
    for i in range(len(df2)):
        # if indicator not yet warmed up, skip
        try:
            stv = float(strat.st.lines.st[i])
        except Exception:
            up.append(False)
            continue
        up.append(df2.loc[i,"close"] > stv)
    return pd.Series(up, name="in_uptrend")

def main():
    symbol, start, end = "MARUTI", "2025-01-01", "2025-06-30"
    periods = [10, 20, 30, 40]
    mults   = [0.8, 1.0, 1.2, 1.5]

    df = load_candles(symbol, start, end)
    results = []
    for p in periods:
        for m in mults:
            up = compute_supertrend(df, p, m)
            shifts = up.astype(int).diff().abs().sum()
            trades = int(shifts // 2)
            win_rate = up.mean() * 100
            results.append({
                "period": p,
                "mult": m,
                "trades": trades,
                "win_rate(%)": round(win_rate, 2)
            })

    out = pd.DataFrame(results)\
            .sort_values(["trades","win_rate(%)"], ascending=[False,False])\
            .reset_index(drop=True)
    print("\nMINI‑SWEEP RESULTS for MARUTI (Jan–Jun 2025)\n")
    print(out.to_string(index=False))

if __name__ == "__main__":
    main()
