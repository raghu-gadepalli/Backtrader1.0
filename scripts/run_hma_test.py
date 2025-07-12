#!/usr/bin/env python3
"""
scripts/run_hma_test.py

Self-contained grid sweep of the 'fast' HMA parameter for three symbols,
writing Sharpe/Drawdown/Trades/Win-rate into an Excel file, with progress prints.
"""
import os
import sys
from pathlib import Path
import argparse

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

# fixed mids and evaluation windows
FIXED_MIDS = {
    "ICICIBANK": {"mid1": 1440, "mid2":  540, "mid3":  900},
    "INFY":      {"mid1": 1680, "mid2":  120, "mid3":  240},
    "RELIANCE":  {"mid1": 1680, "mid2":  180, "mid3":  240},
}

WARMUP_START = "2025-04-01"
EVAL_PERIODS = [
    ("2025-05-01", "2025-05-31", "MAY"),
    ("2025-06-01", "2025-06-30", "JUN")
]

def run_period(symbol, w_start, p_start, p_end, params):
    """
    Run Cerebro from w_start→p_end, report only p_start→p_end metrics.
    Returns a dict with metrics.
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
    parser = argparse.ArgumentParser(description="Grid-sweep 'fast' HMA parameter")
    parser.add_argument("--fasts", nargs="+", type=int, required=True,
                        help="List of 'fast' HMA values to test")
    parser.add_argument("--output", type=Path, default=Path("hma_fast_sweep.xlsx"),
                        help="Excel file to write results")
    args = parser.parse_args()

    fasts = args.fasts
    out_path = args.output
    print(f"Starting HMA fast sweep with fasts={fasts}, output→ {out_path}\n")

    results = []
    total_iters = len(fasts) * len(FIXED_MIDS) * len(EVAL_PERIODS)
    iter_count = 0

    for fast in fasts:
        print(f"=== Testing fast = {fast} ===")
        for symbol, mids in FIXED_MIDS.items():
            print(f"  ↳ Symbol: {symbol}")
            params = {"fast": fast, **mids, "atr_mult": 0.0}

            for p_start, p_end, label in EVAL_PERIODS:
                iter_count += 1
                print(f"    [{iter_count}/{total_iters}] Period {label}: {p_start}→{p_end} ...", end=" ")
                
                row = run_period(symbol, WARMUP_START, p_start, p_end, params)
                print(f"Sharpe={row['sharpe']}, Trades={row['trades']}, Win={row['win_rate']}%")
                
                results.append(row)

    # build DataFrame and write to Excel
    df = pd.DataFrame(results)
    df = df[["symbol", "fast", "period", "sharpe", "drawdown", "trades", "win_rate", "wins", "losses"]]
    df.to_excel(out_path, index=False)
    print(f"\nDone! Results written to {out_path}")

if __name__ == "__main__":
    main()
