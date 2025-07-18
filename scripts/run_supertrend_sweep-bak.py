#!/usr/bin/env python3
# scripts/run_supertrend_sweep.py

import os
import sys
import numpy as np
import backtrader as bt
import pandas as pd

os.environ["MPLBACKEND"] = "Agg"
import matplotlib; matplotlib.use("Agg", force=True)

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.load_candles import load_candles
from strategies.supertrend import ST

SYMBOLS = ["MARUTI", "NIFTY 50", "NIFTY BANK"]
PERIODS = [20, 30, 40, 60, 80, 120, 160, 180, 240]
MULTS   = [1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0]

WINDOWS = [
    {"label": "Jan-Jun", "warm": "2024-12-01", "start": "2025-01-01", "end": "2025-06-30"},
    {"label": "Jan-Feb", "warm": "2025-01-01", "start": "2025-02-01", "end": "2025-02-28"},
    {"label": "Feb-Mar", "warm": "2025-02-01", "start": "2025-03-01", "end": "2025-03-31"},
    {"label": "Mar-Apr", "warm": "2025-03-01", "start": "2025-04-01", "end": "2025-04-30"},
]

RESULTS_CSV = "supertrend_sweep_results.csv"
results = []

def run_sweep(symbol, window, period, mult):
    df = load_candles(symbol, window["warm"], window["end"])
    df.index = pd.to_datetime(df.index)

    # Compute volatility baseline
    tmp = df.copy()
    tmp["prev_close"] = tmp["close"].shift(1)
    tmp["tr"] = np.maximum(
        tmp["high"] - tmp["low"],
        np.maximum(
            (tmp["high"] - tmp["prev_close"]).abs(),
            (tmp["low"]  - tmp["prev_close"]).abs()
        )
    )
    vol_baseline = tmp.loc[window["start"]:window["end"], "tr"].mean()

    cerebro = bt.Cerebro()
    cerebro.broker.set_coc(True)      # execute orders at the bar’s close
    cerebro.broker.setcash(500_000)   # ample cash so orders don’t reject
    cerebro.broker.setcommission(commission=0.0002)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    data = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=1,
        fromdate=pd.to_datetime(window["warm"]),
        todate=pd.to_datetime(window["end"]),
    )
    cerebro.adddata(data, name=symbol)

    cerebro.addstrategy(
        ST,
        st_period=period,
        st_mult=mult,
        eval_start=pd.to_datetime(window["start"])
    )

    strat = cerebro.run()[0]
    sr = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    dd = strat.analyzers.drawdown.get_analysis().max.drawdown
    trd = strat.analyzers.trades.get_analysis()
    won = trd.get("won", {}).get("total", 0)
    lost = trd.get("lost", {}).get("total", 0)
    tot = trd.get("total", {}).get("closed", 0)
    wr = (won / tot * 100) if tot else 0.0

    print(f"\n--- {symbol} | {window['label']} @ ST({period},{mult}) "
          f"[vol_baseline={vol_baseline:.4f}] ---")
    print(f"Sharpe Ratio : {sr:.2f}")
    print(f"Max Drawdown : {dd:.2f}%")
    print(f"Total Trades : {tot}")
    print(f"Win Rate     : {wr:.1f}% ({won}W/{lost}L)")

    result_entry = {
        "symbol": symbol,
        "window": window["label"],
        "period": period,
        "mult": mult,
        "vol_baseline": vol_baseline,
        "sharpe": sr,
        "drawdown": dd,
        "trades": tot,
        "win_rate": wr,
    }

    results.append(result_entry)

    # Incremental write (append mode)
    result_df = pd.DataFrame([result_entry])
    header = not os.path.exists(RESULTS_CSV)
    result_df.to_csv(RESULTS_CSV, mode='a', index=False, header=header)

if __name__ == "__main__":
    # Remove existing results file at start to avoid duplicate entries
    if os.path.exists(RESULTS_CSV):
        os.remove(RESULTS_CSV)

    for symbol in SYMBOLS:
        for period in PERIODS:
            for mult in MULTS:
                for w in WINDOWS:
                    run_sweep(symbol, w, period, mult)

    print(f"\nResults incrementally written to {RESULTS_CSV}")
