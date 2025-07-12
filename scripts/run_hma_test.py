#!/usr/bin/env python3
"""
scripts/run_hma_test.py

Self-contained grid sweep of the 'fast' HMA parameter for three symbols,
writing Sharpe/Drawdown/Trades/Win‐rate into an Excel file, with progress prints.

FASTS and OUTPUT_PATH are hard-coded at the top of the file; no CLI args needed.
"""
import os
import sys
from pathlib import Path

# force headless plotting for backtrader
os.environ["MPLBACKEND"] = "Agg"
import backtrader as bt

import pandas as pd

# adjust this import if your project structure differs
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles                   import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

# ─────── HARD-CODED SETTINGS ─────────

# List of 'fast' HMA values to test
FASTS = [30, 60, 120, 180, 240]

# Output Excel file
OUTPUT_PATH = Path("hma_fast_sweep.xlsx")

# Fixed mid legs (must satisfy fast < mid1 < mid2 < mid3)
FIXED_MIDS = {
    "ICICIBANK": {"mid1":  540, "mid2":  900, "mid3": 1440},
    "INFY":      {"mid1":  120, "mid2":  240, "mid3": 1680},
    "RELIANCE":  {"mid1":  180, "mid2":  240, "mid3": 1680},
}

# Warm-up start and evaluation periods
WARMUP_START = "2025-04-01"
EVAL_PERIODS = [
    ("2025-05-01", "2025-05-31", "MAY"),
    ("2025-06-01", "2025-06-30", "JUN")
]

# ─────── END HARD-CODED SETTINGS ──────

def run_period(symbol, w_start, p_start, p_end, params):
    """
    Run Cerebro from w_start→p_end, return metrics for p_start→p_end.
    """
    cerebro = bt.Cerebro()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    df = load_candles(symbol, w_start, p_end)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(HmaStateStrengthStrategy,
                        fast     = params["fast"],
                        mid1     = params["mid1"],
                        mid2     = params["mid2"],
                        mid3     = params["mid3"],
                        atr_mult = params["atr_mult"],
                        printlog = False)

    strat = cerebro.run()[0]
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd     = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr     = strat.analyzers.trades.get_analysis()
    won    = tr.get("won", {}).get("total", 0)
    lost   = tr.get("lost", {}).get("total", 0)
    total  = tr.get("total", {}).get("closed", 0)
    winr   = (won / total * 100) if total else 0.0

    return {
        "symbol":    symbol,
        "fast":      params["fast"],
        "period":    f"{p_start}-{p_end}",
        "sharpe":    round(sharpe, 4),
        "drawdown":  round(dd, 2),
        "trades":    total,
        "win_rate":  round(winr, 1),
        "wins":      won,
        "losses":    lost
    }

def main():
    print(f"Starting HMA fast sweep: FASTS={FASTS}, OUTPUT={OUTPUT_PATH}\n")

    results = []
    total_iters = len(FASTS) * len(FIXED_MIDS) * len(EVAL_PERIODS)
    iter_count = 0

    for fast in FASTS:
        print(f"=== Testing fast = {fast} ===")
        for symbol, mids in FIXED_MIDS.items():
            # enforce ordering constraint
            if not (fast < mids["mid1"] < mids["mid2"] < mids["mid3"]):
                print(f"  ↳ Skipping {symbol}: fast({fast}) !< mid1({mids['mid1']}) < mid2({mids['mid2']}) < mid3({mids['mid3']})")
                continue

            print(f"  ↳ Symbol: {symbol}")
            params = {"fast": fast, **mids, "atr_mult": 0.0}

            for p_start, p_end, label in EVAL_PERIODS:
                iter_count += 1
                print(f"    [{iter_count}/{total_iters}] {label} {p_start}→{p_end} ...", end=" ")

                row = run_period(symbol, WARMUP_START, p_start, p_end, params)
                print(f"Sharpe={row['sharpe']}, Trades={row['trades']}, Win={row['win_rate']}%")

                results.append(row)

    # build DataFrame and write to Excel
    df = pd.DataFrame(results)
    df = df[["symbol", "fast", "period", "sharpe", "drawdown", "trades", "win_rate", "wins", "losses"]]
    df.to_excel(OUTPUT_PATH, index=False)
    print(f"\nDone! Results written to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
