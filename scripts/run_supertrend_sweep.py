#!/usr/bin/env python3
# scripts/run_supertrend_sweep.py

import os
import sys
import csv
from itertools import product
from datetime import datetime
import pandas as pd
import numpy as np
import backtrader as bt

# ─── project root ─────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ────────────────────────────────────────────────────────────────────────────────

from data.load_candles     import load_candles
from strategies.supertrend import ST

# ─── CONFIG ────────────────────────────────────────────────────────────────────
# SYMBOLS    = [
#     "AXISBANK", "HDFCBANK", "ICICIBANK", "INFY", "KOTAKBANK",
#     "MARUTI", "NIFTY 50", "NIFTY BANK", "RELIANCE",
#     "SBIN", "SUNPHARMA", "TATAMOTORS", "TCS", "TECHM"
# ]

SYMBOLS    = ["AXISBANK"]


PERIODS    = [20, 30, 40, 60, 80, 120, 160, 180, 240]
MULTS      = [1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0]
WARMUP     = "2024-12-01"
END_FULL   = "2025-07-17"   # or today
RESULTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../results"))
RESULTS_CSV = os.path.join(RESULTS_DIR, "supertrend_sweep_results.csv")
# ────────────────────────────────────────────────────────────────────────────────

# ─── Analyzer to record per‑trade net PnL ────────────────────────────────────────
class PnLAnalyzer(bt.Analyzer):
    def __init__(self):
        super().__init__()
        self.pnls = []

    def notify_trade(self, trade):
        if trade.isclosed:
            # record net PnL including commission
            self.pnls.append(trade.pnlcomm)

    def get_analysis(self):
        return self.pnls

# ─── Build Cerebro with all analyzers ───────────────────────────────────────────
def make_cerebro():
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)
    cerebro.broker.setcash(500_000)
    cerebro.broker.setcommission(commission=0.0002)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(PnLAnalyzer,                _name="pnl")
    return cerebro

# ─── Monthly window builder ────────────────────────────────────────────────────
def build_monthly_windows(start_full, end_full):
    start_dt = pd.to_datetime(start_full)
    end_dt   = pd.to_datetime(end_full)
    windows = []
    for ms in pd.date_range(start_dt, end_dt, freq="MS"):
        me = ms + pd.offsets.MonthEnd(0)
        if me > end_dt:
            me = end_dt
        windows.append({
            "label": ms.strftime("%b-%Y"),
            "warm":  start_full,
            "start": ms.strftime("%Y-%m-%d"),
            "end":   me.strftime("%Y-%m-%d")
        })
    return windows

# ─── Main sweep ─────────────────────────────────────────────────────────────────
def run_sweep():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    windows = build_monthly_windows(WARMUP, END_FULL)

    write_header = not os.path.exists(RESULTS_CSV)
    f = open(RESULTS_CSV, "a", newline="")
    writer = csv.writer(f)
    if write_header:
        writer.writerow([
            "symbol","window","period","mult","vol_baseline",
            "sharpe","drawdown","trades","win_rate","expectancy"
        ])

    for symbol in SYMBOLS:
        print(f"\n=== {symbol} ===")
        # load full history
        df_full = load_candles(
            symbol,
            f"{WARMUP} 00:00:00",
            f"{END_FULL} 23:59:59"
        )
        df_full.index = pd.to_datetime(df_full.index)
        # compute True Range
        df_full["prev_close"] = df_full["close"].shift(1)
        df_full["TR"] = np.maximum(
            df_full["high"] - df_full["low"],
            np.maximum(
                (df_full["high"] - df_full["prev_close"]).abs(),
                (df_full["low"]  - df_full["prev_close"]).abs()
            )
        )
        # precompute vol_baseline per window
        vol_map = {}
        for w in windows:
            mask = (df_full.index >= w["start"]) & (df_full.index <= w["end"])
            vol_map[w["label"]] = df_full.loc[mask, "TR"].mean()

        # sweep
        for w in windows:
            label = w["label"]
            vb    = vol_map[label]
            df_win = df_full.loc[df_full.index <= pd.to_datetime(w["end"])]

            for period, mult in product(PERIODS, MULTS):
                cerebro = make_cerebro()

                data = bt.feeds.PandasData(
                    dataname    = df_win,
                    timeframe   = bt.TimeFrame.Minutes,
                    compression = 1,
                    fromdate    = datetime.strptime(
                        w["warm"] + " 00:00:00", "%Y-%m-%d %H:%M:%S"),
                    todate      = datetime.strptime(
                        w["end"]  + " 23:59:59", "%Y-%m-%d %H:%M:%S"),
                )
                cerebro.adddata(data, name=symbol)

                cerebro.addstrategy(
                    ST,
                    st_period  = period,
                    st_mult    = mult,
                    eval_start = datetime.strptime(
                        w["start"] + " 00:00:00", "%Y-%m-%d %H:%M:%S")
                )

                strat = cerebro.run()[0]

                # analyzers
                sr   = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
                dd   = strat.analyzers.drawdown.get_analysis().max.drawdown
                tr   = strat.analyzers.trades.get_analysis()
                won  = tr.get("won",  {}).get("total", 0)
                tot  = tr.get("total",{}).get("closed", 0)
                wr   = (won/tot*100) if tot else 0.0

                # expectancy
                pnls = strat.analyzers.pnl.get_analysis()
                wins   = [p for p in pnls if p>0]
                losses = [abs(p) for p in pnls if p<=0]
                avg_win  = sum(wins)/len(wins)     if wins   else 0.0
                avg_loss = sum(losses)/len(losses) if losses else 0.0
                win_pct  = len(wins)/len(pnls)      if pnls   else 0.0
                expectancy = win_pct*avg_win - (1-win_pct)*avg_loss

                # write & flush
                writer.writerow([
                    symbol, label, period, mult, f"{vb:.6f}",
                    f"{sr:.6f}", f"{dd:.6f}", tot, f"{wr:.2f}",
                    f"{expectancy:.6f}"
                ])
                f.flush()

                print(f"{symbol} | {label} | ST({period},{mult}) → "
                      f"Sharpe {sr:.2f}, Trades {tot}, Win {wr:.1f}%, Exp {expectancy:.2f}")

    f.close()
    print(f"\nSweep results streaming into → {RESULTS_CSV}")

if __name__ == "__main__":
    run_sweep()
