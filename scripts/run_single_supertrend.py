#!/usr/bin/env python3
# scripts/run_july_supertrend.py

import os
import sys
from datetime import datetime
import pandas as pd
import backtrader as bt

# ─── project root setup ───────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ────────────────────────────────────────────────────────────────────────────────

from data.load_candles     import load_candles
from strategies.supertrend import ST

# — single symbol & SuperTrend params —————————————————————————————————————
SYMBOL      = "AXISBANK"
ST_PERIOD   = 120
ST_MULT     = 2.6

# — dates: warm‑up through end of July 17 —————————————————————————————————
WARMUP     = "2025-04-01"
TEST_START = "2025-07-01"
TEST_END   = "2025-07-17"

def normalize(ts, is_start):
    return ts + (" 00:00:00" if is_start else " 23:59:59")

# ─── analyzer to capture each trade's net PnL ───────────────────────────────────
class PnLAnalyzer(bt.Analyzer):
    def __init__(self):
        self.pnls = []
    def notify_trade(self, trade):
        if trade.isclosed:
            self.pnls.append(trade.pnlcomm)
    def get_analysis(self):
        return self.pnls

# ─── debug strategy that reuses ST but no per‑bar prints ───────────────────────
class STDebug(ST):
    def notify_order(self, order):
        # suppress per‑bar prints; only execution logs if you want them
        pass
    def notify_trade(self, trade):
        # suppress per‑bar prints; PnL captured by analyzer
        pass

# ────────────────────────────────────────────────────────────────────────────────
def run_july():
    warm_ts  = normalize(WARMUP,    True)
    start_ts = normalize(TEST_START, True)
    end_ts   = normalize(TEST_END,   False)

    # 1) load candles
    df = load_candles(SYMBOL, warm_ts, end_ts)
    df.index = pd.to_datetime(df.index)
    print(f"\n{SYMBOL}: loaded {len(df)} bars from {warm_ts} to {end_ts}")

    # 2) Cerebro setup
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_coc(True)                  # fill at bar close
    cerebro.broker.setcash(500_000)               # ample cash
    cerebro.broker.setcommission(commission=0.0002)

    # analyzers
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(PnLAnalyzer,                _name="pnl")

    # 3) feed data
    data = bt.feeds.PandasData(
        dataname    = df,
        fromdate    = datetime.strptime(warm_ts,  "%Y-%m-%d %H:%M:%S"),
        todate      = datetime.strptime(end_ts,   "%Y-%m-%d %H:%M:%S"),
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1,
    )
    cerebro.adddata(data, name=SYMBOL)

    # 4) add SuperTrend strategy
    cerebro.addstrategy(
        STDebug,
        st_period   = ST_PERIOD,
        st_mult     = ST_MULT,
        eval_start  = datetime.strptime(start_ts, "%Y-%m-%d %H:%M:%S")
    )

    # 5) run backtest
    strat = cerebro.run()[0]

    # 6) collect trade stats
    tr    = strat.analyzers.trades.get_analysis()
    total = tr.get("total", {}).get("closed", 0)
    won   = tr.get("won",   {}).get("total",  0)
    lost  = tr.get("lost",  {}).get("total",  0)
    winp  = (won/total*100) if total else 0.0

    # 7) compute expectancy
    pnls      = strat.analyzers.pnl.get_analysis()
    wins      = [p for p in pnls if p>0]
    losses    = [abs(p) for p in pnls if p<=0]
    avg_win   = sum(wins)/len(wins)     if wins   else 0.0
    avg_loss  = sum(losses)/len(losses) if losses else 0.0
    win_pct   = len(wins)/len(pnls)      if pnls   else 0.0
    expectancy = win_pct*avg_win - (1-win_pct)*avg_loss

    # 8) print summary
    print(f"\n--- {SYMBOL} | July 1–17, 2025 @ ST({ST_PERIOD},{ST_MULT}) ---")
    print(f"Total Trades : {total}")
    print(f"Win Rate     : {winp:.1f}% ({won}W/{lost}L)")
    print(f"Avg Win      : {avg_win:.2f}")
    print(f"Avg Loss     : {avg_loss:.2f}")
    print(f"Expectancy   : {expectancy:.2f} (P&L per trade)\n")

if __name__ == "__main__":
    run_july()
