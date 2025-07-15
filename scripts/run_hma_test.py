#!/usr/bin/env python3
# scripts/run_hma_test.py

import os, sys
import pandas as pd

# force headless plotting
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

# ─── project root on path ─────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles                   import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ─── your “time-based” HMA lookbacks (in minutes) ─────────────────────────────
MIN_FAST  = 80    # 80 minutes
MIN_SLOW  = 120   # 120 minutes
# mid2/mid3 are inert for a pure crossover
# ATR filter left off here for brevity
# ──────────────────────────────────────────────────────────────────────────────

# which sampling rates (in minutes) to try
SAMPLES = [1, 2, 3, 5]

# symbols & params (we’ll ignore mid2/mid3 and set them = slow_bars)
SYMBOLS = ["INFY", "RELIANCE"]
PARAMS  = {
    "INFY":     dict(atr_mult=0.0),
    "RELIANCE": dict(atr_mult=0.0),
}

WARMUP_START = "2025-04-01"
TRAIN_START  = "2025-05-01"
TRAIN_END    = "2025-05-31"
TEST_START   = "2025-06-01"
TEST_END     = "2025-06-30"

def run_sample(symbol, sample_min, period_start, period_end):
    # 1) resample
    df = load_candles(symbol, WARMUP_START, period_end)
    df.index = pd.to_datetime(df.index)
    df_s = (
        df.resample(f"{sample_min}min")
          .agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"})
          .dropna()
    )

    # 2) compute BAR counts to preserve minute lookbacks
    fast_bars  = max(1, int(round(MIN_FAST  / sample_min)))
    slow_bars  = max(1, int(round(MIN_SLOW  / sample_min)))
    # mid2 = mid3 = slow to disable extra legs
    mid2_bars  = slow_bars
    mid3_bars  = slow_bars

    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    data = bt.feeds.PandasData(dataname=df_s,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=f"{symbol}-{sample_min}m")

    cerebro.addstrategy(HmaStateStrengthStrategy,
                        fast     = fast_bars,
                        mid1     = slow_bars,
                        mid2     = mid2_bars,
                        mid3     = mid3_bars,
                        atr_mult = PARAMS[symbol]["atr_mult"],
                        printlog = False)

    strat = cerebro.run()[0]
    sa = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr = strat.analyzers.trades.get_analysis()
    won, lost = tr.get("won",{}).get("total",0), tr.get("lost",{}).get("total",0)
    total = tr.get("total",{}).get("closed",0)
    winr  = (won/total*100) if total else 0.0

    print(f"\n--- {symbol} | {period_start}→{period_end} @ {sample_min}m "
          f"(HMA={fast_bars}⇔{slow_bars} bars ≈{fast_bars*sample_min}⇔{slow_bars*sample_min}min) ---")
    print(f"Sharpe Ratio : {sa:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winr:.1f}% ({won}W/{lost}L)")

if __name__ == "__main__":
    for sym in SYMBOLS:
        for sample in SAMPLES:
            # train
            run_sample(sym, sample, TRAIN_START, TRAIN_END)
            # test
            run_sample(sym, sample, TEST_START, TEST_END)
