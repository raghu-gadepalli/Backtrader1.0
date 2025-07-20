#!/usr/bin/env python3
import os, sys

# ─── project root setup ───────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ────────────────────────────────────────────────────────────────────────────────

from datetime import datetime
import pandas as pd
from data.load_candles import load_candles

# ─── USER SETTINGS ─────────────────────────────────────────────────────────────
SYMBOLS = [
    "AXISBANK", "HDFCBANK", "ICICIBANK", "INFY", "KOTAKBANK",
    "MARUTI", "NIFTY 50", "NIFTY BANK", "RELIANCE", "SBIN",
    "SUNPHARMA", "TATAMOTORS", "TCS", "TECHM"
]

# date range for your test
START = "2025-07-01"
END   = "2025-07-17"

MIN_RANGE_PCT = 2.0    # minimum high‑low range over the period
MIN_ATR_PCT   = 0.30   # minimum ATR(14) on 60 min bars, expressed as %

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def normalize(ts, is_start=True):
    return ts + (" 00:00:00" if is_start else " 23:59:59")

def compute_range_pct(df):
    hi, lo = df["high"].max(), df["low"].min()
    return (hi - lo) / lo * 100.0

def compute_hourly_atr_pct(df, period=14):
    """
    Resample the 1 min df to 60 min bars,
    compute ATR(period) on those bars, and
    return the last ATR as a % of last close.
    """
    # Resample to hourly OHLC
    ohlc = pd.DataFrame({
        "open":  df["open"].resample("60min").first(),
        "high":  df["high"].resample("60min").max(),
        "low":   df["low"].resample("60min").min(),
        "close": df["close"].resample("60min").last(),
    }).dropna()

    # True Range
    prev_close = ohlc["close"].shift(1)
    tr = pd.concat([
        ohlc["high"] - ohlc["low"],
        (ohlc["high"] - prev_close).abs(),
        (ohlc["low"]  - prev_close).abs()
    ], axis=1).max(axis=1)

    # ATR rolling
    atr = tr.rolling(period, min_periods=period).mean()

    # last ATR % of last close
    last_atr = atr.iloc[-1]
    last_close = ohlc["close"].iloc[-1]
    return (last_atr / last_close) * 100.0

# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    warm   = normalize(START, True)
    finish = normalize(END,   False)
    dt0 = datetime.strptime(warm,   "%Y-%m-%d %H:%M:%S")
    dt1 = datetime.strptime(finish, "%Y-%m-%d %H:%M:%S")

    print(f"Filtering {START} → {END}")
    print(f" • Minimum range : {MIN_RANGE_PCT:.2f}%")
    print(f" • Minimum ATR%  : {MIN_ATR_PCT:.2f}%  (on 60 min bars)\n")

    results = []
    for sym in SYMBOLS:
        # 1) load minute bars
        df = load_candles(sym, warm, finish)
        df.index = pd.to_datetime(df.index)

        # ensure columns open/high/low/close exist
        df = df[["open", "high", "low", "close"]].dropna()

        # 2) compute range%
        range_pct = compute_range_pct(df)

        # 3) compute hourly ATR%
        atr60_pct = compute_hourly_atr_pct(df, period=14)

        # 4) decide
        ok = (range_pct >= MIN_RANGE_PCT) and (atr60_pct >= MIN_ATR_PCT)
        status = "✅ OK" if ok else "❌ SKIP"

        results.append({
            "symbol":    sym,
            "range%":    f"{range_pct:.2f}%",
            "atr60%":    f"{atr60_pct:.2f}%",
            "status":    status
        })

    # 5) print a nice table
    dfr = pd.DataFrame(results).set_index("symbol")
    print(dfr.to_string())

if __name__ == "__main__":
    # adjust project root if needed
    _ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    main()
