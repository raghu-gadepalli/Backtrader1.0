#!/usr/bin/env python3
"""
Sweep‑style debug of SuperTrend for one symbol/window,
with full CSV dump for bar‑by‑bar comparison.
"""

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import backtrader as bt

# ─ adjust project root if needed ─────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ──────────────────────────────────────────────────────────────────────────────

from data.load_candles import load_candles
from strategies.supertrend import SuperTrend

# ─ PARAMETERS ────────────────────────────────────────────────────────────────
SYMBOL       = "MARUTI"                      # symbol to test
PERIOD       = 20                            # SuperTrend period
MULT         = 3.0                           # SuperTrend multiplier
HISTORY_MULT = 5                             # warm‑up = 5×PERIOD bars
TEST_START   = "2025-07-14 09:15:00"         # window start
TEST_END     = "2025-07-14 15:30:00"         # window end
OUT_CSV      = "maruti_st_debug_full.csv"    # debug dump file
# ──────────────────────────────────────────────────────────────────────────────

def main():
    # 1) compute seed time
    ws = datetime.strptime(TEST_START, "%Y-%m-%d %H:%M:%S")
    history_bars = PERIOD * HISTORY_MULT
    seed_dt = ws - timedelta(minutes=history_bars)
    seed_str = seed_dt.strftime("%Y-%m-%d %H:%M:%S")

    print(f"[INFO] {SYMBOL} ST({PERIOD},{MULT}) | warm‑up = {history_bars} bars")
    print(f"[INFO] Loading {SYMBOL} from {seed_str} → {TEST_END}\n")

    # 2) load candles
    df_full = load_candles(SYMBOL, seed_str, TEST_END)
    df_full.index = pd.to_datetime(df_full.index)
    print(f"[INFO] Loaded {len(df_full)} bars total\n")

    # 3) compute SuperTrend via Backtrader
    data = bt.feeds.PandasData(
        dataname    = df_full,
        datetime    = None,
        open        = 'open',
        high        = 'high',
        low         = 'low',
        close       = 'close',
        volume      = 'volume'
    )
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(data)

    class DebugST(bt.Strategy):
        def __init__(self):
            self.st = SuperTrend(
                self.data,
                period=PERIOD,
                multiplier=MULT
            )
        def next(self):
            pass

    cerebro.addstrategy(DebugST)
    strat = cerebro.run()[0]

    # 4) extract the SuperTrend values into a Series aligned to df_full.index
    st_vals = list(strat.st.lines.st.array)  # numpy array of st values
    # pad/truncate to match df_full length if needed
    # here we assume st_vals == len(df_full)
    df_full['supertrend'] = st_vals

    # 5) dump the full series to CSV
    out = df_full[['close','supertrend']] \
            .reset_index() \
            .rename(columns={'dt':'datetime'})
    out.to_csv(OUT_CSV, index=False)
    print(f"[INFO] Debug CSV written → {OUT_CSV} ({len(out)} rows)\n")

    # 6) slice to test window and print flips
    test = out.set_index('datetime').loc[TEST_START:TEST_END].reset_index()
    test['up'] = test['close'] > test['supertrend']
    test['flip'] = test['up'].astype(int).diff().abs().fillna(0).astype(bool)

    flips = test[test['flip']]
    print(f"Flip Events in {TEST_START}→{TEST_END} ({len(flips)} total):")
    for _, row in flips.iterrows():
        arrow = '⬆' if row['up'] else '⬇'
        print(f"  {row['datetime']}  {arrow} close={row['close']:.2f} st={row['supertrend']:.2f}")

if __name__ == "__main__":
    main()
