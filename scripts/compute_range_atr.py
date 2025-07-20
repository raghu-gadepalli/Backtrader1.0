#!/usr/bin/env python3

import os
import sys

# ─── project root setup ───────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ────────────────────────────────────────────────────────────────────────────────

from data.load_candles import load_candles
import pandas as pd

# ───────── User settings ───────────────────────────────────────────────────────
SYMBOLS    = ['INFY', 'RELIANCE', 'ICICIBANK']
START_DATE = "2024-12-01 00:00:00"
END_DATE   = "2025-07-15 23:59:59"
ATR_PERIOD = 14
# ────────────────────────────────────────────────────────────────────────────────

def compute_tr(df):
    prev = df['close'].shift(1)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev).abs(),
        (df['low']  - prev).abs()
    ], axis=1).max(axis=1)
    return tr

def summarize_atr(atr_series):
    pctiles = [0.10, 0.25, 0.50, 0.75]
    return {f"P{int(p*100)}": round(atr_series.quantile(p),4) for p in pctiles}

def main():
    rows = []
    for sym in SYMBOLS:
        # 1) load minute bars
        df = load_candles(sym, START_DATE, END_DATE)
        df.index = pd.to_datetime(df.index)
        df = df[['high','low','close']].apply(pd.to_numeric, errors='coerce').dropna()

        # 2) compute TR and ATR14
        tr      = compute_tr(df)
        atr14   = tr.rolling(ATR_PERIOD).mean().dropna()

        # 3) compute ATR% (ATR14 / rolling‑median price)
        med14   = df['close'].rolling(ATR_PERIOD).median().loc[atr14.index]
        atr_pct = (atr14 / med14 * 100).dropna()

        # 4) gather stats
        stat = {
            'symbol': sym,
            'atr14_last': round(atr14.iloc[-1],4),
            'atr%_last':  round(atr_pct.iloc[-1],4),
        }
        stat.update({f"atr14_{k}": v for k,v in summarize_atr(atr14).items()})
        stat.update({f"atr%_{k}": v for k,v in summarize_atr(atr_pct).items()})
        rows.append(stat)

    # 5) show results
    df_out = pd.DataFrame(rows).set_index('symbol')
    print("\nATR(14) & ATR%14 summary (Dec 1 → Jul 15):\n")
    print(df_out.to_string())

if __name__ == "__main__":
    main()
