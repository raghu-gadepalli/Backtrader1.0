#!/usr/bin/env python3
# scripts/run_hmamulti_test.py

import os
import sys
import pandas as pd
from datetime import datetime

# headless plotting
os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

import backtrader as bt

# ─── Adjust project root if needed ──────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ─────────────────────────────────────────────────────────────────────────────

# ─── optionally dump CSV into a 'results' folder ────────────────────────────
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

from data.load_candles        import load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy

# ——— Your HMA‑Multi parameters per symbol (ATR/ADX removed) ————————————
HMA_MULTI_PARAMS = {
    "ICICIBANK": dict(
        fast     = 180,
        mid1     = 240,
        mid2     = 360,
        mid3     = 720,
        printlog = False
    ),
    "RELIANCE": dict(
        fast     = 220,
        mid1     = 440,
        mid2     = 800,
        mid3     = 1600,
        printlog = False
    ),
}

SYMBOLS = list(HMA_MULTI_PARAMS.keys())

# Global warm‑up date (must be before any test window)
WARMUP = "2025-04-01"

# Define the windows you want to evaluate
PERIODS = {
    "May-2025":   ("2025-05-01", "2025-05-31"),
    "June-2025":  ("2025-06-01", "2025-06-30"),
    "July-2025":  ("2025-07-01", "2025-07-14"),
}

results = []

def normalize_dt(ds: str, is_start: bool) -> str:
    """Convert 'YYYY-MM-DD' → 'YYYY-MM-DD HH:MM:SS' for start/end."""
    if len(ds) == 10:
        return ds + (" 00:00:00" if is_start else " 23:59:59")
    return ds

def run_period(symbol: str, label: str, start_raw: str, end_raw: str):
    params = HMA_MULTI_PARAMS[symbol]
    start_str = normalize_dt(start_raw, True)
    end_str   = normalize_dt(end_raw, False)
    warm_str  = normalize_dt(WARMUP, True)

    # load full history for warm‑up → end
    df = load_candles(symbol, warm_str, end_str)
    df.index = pd.to_datetime(df.index)

    # set up Cerebro
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)
    cerebro.broker.setcash(500_000)
    cerebro.broker.setcommission(commission=0.0002)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes,
                        riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    data = bt.feeds.PandasData(
        dataname    = df,
        fromdate    = datetime.strptime(warm_str, "%Y-%m-%d %H:%M:%S"),
        todate      = datetime.strptime(end_str,   "%Y-%m-%d %H:%M:%S"),
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1,
    )
    cerebro.adddata(data, name=symbol)

    # only pass the HMA params (ATR/ADX will use their defaults)
    cerebro.addstrategy(
        HmaMultiTrendStrategy,
        fast     = params["fast"],
        mid1     = params["mid1"],
        mid2     = params["mid2"],
        mid3     = params["mid3"],
        printlog = params.get("printlog", False)
    )

    strat = cerebro.run()[0]

    # collect metrics
    sharpe  = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd      = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr      = strat.analyzers.trades.get_analysis()
    won     = tr.get("won",  {}).get("total", 0)
    lost    = tr.get("lost", {}).get("total", 0)
    tot     = tr.get("total",{}).get("closed", 0)
    winrate = (won / tot * 100) if tot else 0.0

    # compute expectancy
    avg_w      = tr.get("won", {}).get("pnl", {}).get("average", 0.0)
    avg_l      = tr.get("lost", {}).get("pnl", {}).get("average", 0.0)
    expectancy = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("nan")

    # print & store
    print(f"\n--- {symbol} | {label} @ HMA_MULTI "
          f"(fast={params['fast']}, mid1={params['mid1']}, "
          f"mid2={params['mid2']}, mid3={params['mid3']}) ---")
    print(f"Warm‑up      → {warm_str}")
    print(f"Eval window → {start_str} to {end_str}")
    print(f"Sharpe Ratio : {sharpe:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {winrate:.1f}% ({won}W/{lost}L)")
    print(f"Expectancy   : {expectancy:.4f}")

    results.append({
        "symbol":       symbol,
        "period_label": label,
        "warmup":       warm_str,
        "start":        start_str,
        "end":          end_str,
        "fast":         params["fast"],
        "mid1":         params["mid1"],
        "mid2":         params["mid2"],
        "mid3":         params["mid3"],
        "sharpe":       sharpe,
        "drawdown":     dd,
        "trades":       tot,
        "win_rate":     winrate,
        "expectancy":   expectancy,
    })

if __name__ == "__main__":
    for sym in SYMBOLS:
        for label, (s, e) in PERIODS.items():
            run_period(sym, label, s, e)

    output_file = os.path.join(RESULTS_DIR, "hma_multi_test_results.csv")
    pd.DataFrame(results).to_csv(output_file, index=False)
    print(f"\nWrote {output_file}")
