#!/usr/bin/env python3
# scripts/run_supertrend_test.py

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

from data.load_candles    import load_candles
from strategies.supertrend import ST

# ——— Your SuperTrend parameters per symbol —————————————————————————————
ST_PARAMS = {
    # "AXISBANK":   dict(period=30, mult=12.0),
    # "HDFCBANK":   dict(period=30, mult=12.0),
    "ICICIBANK":  dict(period=60, mult=3.0),
    "INFY":       dict(period=60, mult=3.0),
    # "KOTAKBANK":  dict(period=30, mult=12.0),
    # "MARUTI":     dict(period=30, mult=12.0),
    # "NIFTY 50":   dict(period=30, mult=12.0),
    # "NIFTY BANK": dict(period=30, mult=12.0),
    "RELIANCE":   dict(period=60, mult=3.0),
    # "SBIN":       dict(period=30, mult=12.0),
    # "SUNPHARMA":  dict(period=30, mult=12.0),
    # "TATAMOTORS": dict(period=30, mult=12.0),
    # "TCS":        dict(period=30, mult=6.0),
    # "TECHM":      dict(period=30, mult=12.0),
}

SYMBOLS = list(ST_PARAMS.keys())

# Global warm-up date (must be well before any test window)
WARMUP = "2025-06-25"

# Define only the windows you actually want to evaluate; date‑only is OK
PERIODS = {
    "July-2025": ("2025-07-01", "2025-07-17"),
    # "May-2025":   ("2025-05-01", "2025-05-31"),
    # etc...
}

results = []

def normalize_dt(ds: str, is_start: bool) -> str:
    """Convert 'YYYY-MM-DD' → 'YYYY-MM-DD HH:MM:SS' for start/end."""
    if len(ds) == 10:
        return ds + (" 00:00:00" if is_start else " 23:59:59")
    return ds

def run_period(symbol: str, label: str, start_raw: str, end_raw: str):
    params = ST_PARAMS[symbol]
    period = params["period"]

    # build full timestamps
    start_str = normalize_dt(start_raw, True)
    end_str   = normalize_dt(end_raw,  False)
    start_dt  = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
    end_dt    = datetime.strptime(end_str,   "%Y-%m-%d %H:%M:%S")
    warm_str  = normalize_dt(WARMUP, True)

    # 1) load warm‑up → end
    df = load_candles(symbol, warm_str, end_str)
    df.index = pd.to_datetime(df.index)

    # 2) set up Cerebro
    cerebro = bt.Cerebro()
    cerebro.broker.set_coc(True)      # execute orders at the bar’s close
    cerebro.broker.setcash(500_000)   # ample cash so orders don’t reject
    cerebro.broker.setcommission(commission=0.0002)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    # 3) feed full history
    data = bt.feeds.PandasData(
        dataname    = df,
        fromdate    = datetime.strptime(warm_str, "%Y-%m-%d %H:%M:%S"),
        todate      = end_dt,
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1,
    )
    cerebro.adddata(data, name=symbol)

    # 4) add your strategy, only eval from start_dt
    cerebro.addstrategy(ST, st_period=period, st_mult=params["mult"])

    strat = cerebro.run()[0]

    # 5) collect metrics
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

    # 6) print and record
    print(f"\n--- {symbol} | {label} @ ST({period},{params['mult']}) ---")
    print(f"Warmup      → {warm_str}")
    print(f"Eval window → {start_str} to {end_str}")
    print(f"Sharpe Ratio : {sharpe:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {winrate:.1f}% ({won}W/{lost}L)")
    print(f"Expectancy   : {expectancy:.4f}")

    results.append({
        "symbol":        symbol,
        "period_label":  label,
        "warmup":        warm_str,
        "start":         start_str,
        "end":           end_str,
        "st_period":     period,
        "st_mult":       params["mult"],
        "sharpe":        sharpe,
        "drawdown":      dd,
        "trades":        tot,
        "win_rate":      winrate,
        "expectancy":    expectancy,
    })

if __name__ == "__main__":
    for sym in SYMBOLS:
        for label, (s, e) in PERIODS.items():
            run_period(sym, label, s, e)

    output_file = os.path.join(RESULTS_DIR, "supertrend_test_results.csv")
    pd.DataFrame(results).to_csv(output_file, index=False)
    print(f"\nWrote {output_file}")
