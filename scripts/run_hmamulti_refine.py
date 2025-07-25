#!/usr/bin/env python3
"""
scripts/run_hmamulti_refine.py

Stage2 refinement for multiHMA: for one or more symbols, test a manuallypicked
list of HMA parameter combos and dump results (with expectancy) to
results/<SYMBOL>_hma_refine.csv.
"""

import os
import sys
import csv

#  project root on path 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

#  dump CSVs into a 'results' folder 
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

import backtrader as bt
from data.load_candles         import load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy

#  SETTINGS 
WARMUP_START  = "2025-04-01"
END           = "2025-07-06"
ATR_MULT      = 0.0
STARTING_CASH = 500_000
COMMISSION    = 0.0002

#  Manuallypicked combos per symbol for refinement 
# Only include the symbols you want to refine in this dict:
COMBINATIONS = {
    "INFY": [
        {"fast":  50, "mid1": 150, "mid2": 300,  "mid3":  600},
        {"fast":  70, "mid1": 210, "mid2": 420,  "mid3":  840},
        {"fast": 100, "mid1": 300, "mid2": 600,  "mid3": 1200},
    ],
    "RELIANCE": [
        {"fast": 220, "mid1": 440, "mid2":  800, "mid3": 1600},
        {"fast": 240, "mid1": 480, "mid2":  960, "mid3": 1920},  # current best
        {"fast": 260, "mid1": 520, "mid2": 1040, "mid3": 2080},
    ],
}
def make_cerebro():
    """
    Build a Cerebro instance with broker settings and analyzers.
    """
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)
    cerebro.broker.setcash(STARTING_CASH)
    cerebro.broker.setcommission(commission=COMMISSION)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    return cerebro

def backtest(symbol, fast, mid1, mid2, mid3, atr_mult):
    """
    Run one backtest and return (sharpe, expectancy, total_trades, win_rate%).
    """
    cerebro = make_cerebro()
    df      = load_candles(symbol, WARMUP_START, END)
    data    = bt.feeds.PandasData(
        dataname    = df,
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1
    )
    cerebro.adddata(data)
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
    # Sharpe ratio
    s = strat.analyzers.sharpe.get_analysis().get("sharperatio") or 0.0
    # Trades analysis
    tr   = strat.analyzers.trades.get_analysis()
    won  = tr.get("won",{}).get("total", 0)
    lost = tr.get("lost",{}).get("total", 0)
    tot  = won + lost
    # Expectancy (avg win/loss weighted by win%)
    avg_w = tr.get("won",{}).get("pnl",{}).get("average", 0.0)
    avg_l = tr.get("lost",{}).get("pnl",{}).get("average", 0.0)
    e     = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("nan")
    # Win rate %
    wr    = (won/tot*100) if tot else 0.0

    return s, e, tot, wr

def run_refine():
    for symbol, combos in COMBINATIONS.items():
        out_csv = os.path.join(RESULTS_DIR, f"{symbol}_hma_refine.csv")
        print(f"\nRefining {symbol}  writing to {out_csv}")
        with open(out_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "fast","mid1","mid2","mid3",
                "sharpe","expectancy","trades","win_rate"
            ])
            f.flush()

            for combo in combos:
                fast, mid1 = combo["fast"], combo["mid1"]
                mid2, mid3 = combo["mid2"], combo["mid3"]
                print(f"  Testing HMA({fast},{mid1},{mid2},{mid3}) ...")
                s, e, tot, wr = backtest(symbol, fast, mid1, mid2, mid3, ATR_MULT)
                writer.writerow([
                    fast, mid1, mid2, mid3,
                    f"{s:.6f}", f"{e:.6f}",
                    tot, f"{wr:.2f}"
                ])
                f.flush()

if __name__ == "__main__":
    run_refine()
