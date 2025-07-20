#!/usr/bin/env python3
# scripts/run_hma_multi_sweep.py

import os, sys, csv
from itertools import product
from datetime import datetime
import pandas as pd
import backtrader as bt

# ─── project root setup ───────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ────────────────────────────────────────────────────────────────────────────────

from data.load_candles     import load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy

# ─── CONFIG ──────────────────────────────────────────────────────────────────
SYMBOLS      = ["ICICIBANK", "INFY", "RELIANCE"]
WARMUP_START = "2025-04-01"
END_FULL     = "2025-07-06"

# HMA parameter grid (common across all symbols)
FAST_PERIODS = [30, 60, 90, 120, 150, 180]
MID1_PERIODS = [120, 240, 360, 480]
MID2_PERIODS = [240, 360, 480, 720]
MID3_PERIODS = [480, 720, 960, 1440]

ATR_MULT     = 0.0
STARTING_CASH   = 500_000
COMMISSION_RATE = 0.0002

# where to dump results
RESULTS_DIR = os.path.join(_ROOT, "results")
RESULTS_CSV = os.path.join(RESULTS_DIR, "hma_multi_sweep_results.csv")

# ─── build monthly windows ───────────────────────────────────────────────────
def build_monthly_windows(start_full: str, end_full: str):
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
            "end":   me.strftime("%Y-%m-%d"),
        })
    return windows

# ─── Cerebro factory ─────────────────────────────────────────────────────────
class PnLAnalyzer(bt.Analyzer):
    def __init__(self):
        super().__init__()
        self.pnls = []
    def notify_trade(self, trade):
        if trade.isclosed:
            self.pnls.append(trade.pnlcomm)
    def get_analysis(self):
        return self.pnls

def make_cerebro():
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)
    cerebro.broker.setcash(STARTING_CASH)
    cerebro.broker.setcommission(commission=COMMISSION_RATE)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(PnLAnalyzer,               _name="pnl")
    return cerebro

# ─── single backtest ─────────────────────────────────────────────────────────
def backtest(symbol, fast, mid1, mid2, mid3, atr_mult, warm, end):
    # load full history for this symbol up to window end
    df = load_candles(symbol,
                      f"{WARMUP_START} 00:00:00",
                      f"{END_FULL} 23:59:59")
    df.index = pd.to_datetime(df.index)
    # slice to window end
    df_win = df.loc[df.index <= pd.to_datetime(end)]

    cerebro = make_cerebro()
    data = bt.feeds.PandasData(
        dataname    = df_win,
        fromdate    = datetime.strptime(f"{warm} 00:00:00", "%Y-%m-%d %H:%M:%S"),
        todate      = datetime.strptime(f"{end} 23:59:59", "%Y-%m-%d %H:%M:%S"),
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1,
    )
    cerebro.adddata(data, name=symbol)
    cerebro.addstrategy(
        HmaMultiTrendStrategy,
        fast     = fast,
        mid1     = mid1,
        mid2     = mid2,
        mid3     = mid3,
        atr_mult = atr_mult,
        printlog = False
    )

    strat = cerebro.run()[0]
    # Sharpe
    sr   = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0.0) or 0.0
    # Trades
    tr   = strat.analyzers.trades.get_analysis()
    won  = tr.get("won", {}).get("total", 0)
    lost = tr.get("lost", {}).get("total", 0)
    tot  = tr.get("total",{}).get("closed", 0)
    wr   = (won/tot*100) if tot else 0.0
    # Expectancy from PnL
    pnls     = strat.analyzers.pnl.get_analysis()
    wins     = [p for p in pnls if p>0]
    losses   = [abs(p) for p in pnls if p<=0]
    avg_w    = sum(wins)/len(wins)     if wins   else 0.0
    avg_l    = sum(losses)/len(losses) if losses else 0.0
    win_pct  = len(wins)/len(pnls)      if pnls   else 0.0
    expectancy = win_pct*avg_w - (1-win_pct)*avg_l

    return sr, expectancy, tot, wr

# ─── main sweep ──────────────────────────────────────────────────────────────
def run_sweep():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    windows = build_monthly_windows(WARMUP_START, END_FULL)

    write_header = not os.path.exists(RESULTS_CSV)
    with open(RESULTS_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "symbol","window",
                "fast","mid1","mid2","mid3",
                "sharpe","expectancy","trades","win_rate"
            ])

        for w in windows:
            label = w["label"]
            warm  = w["warm"]
            end   = w["end"]

            for symbol in SYMBOLS:
                print(f"\n=== {symbol} | {label} ===")
                # sweep all HMA combos
                for fast, mid1, mid2, mid3 in product(
                        FAST_PERIODS, MID1_PERIODS, MID2_PERIODS, MID3_PERIODS):
                    if not (fast < mid1 < mid2 < mid3):
                        continue
                    sr, expc, tot, wr = backtest(
                        symbol, fast, mid1, mid2, mid3,
                        ATR_MULT, warm, end
                    )
                    writer.writerow([
                        symbol, label,
                        fast, mid1, mid2, mid3,
                        f"{sr:.6f}", f"{expc:.6f}", tot, f"{wr:.2f}"
                    ])
                    f.flush()
                    print(f"→ HMA({fast},{mid1},{mid2},{mid3})  "
                          f"Sharpe {sr:.2f}, Trades {tot}, Win {wr:.1f}%, Exp {expc:.2f}")

    print(f"\nSweep results streaming into → {RESULTS_CSV}")

if __name__ == "__main__":
    run_sweep()
