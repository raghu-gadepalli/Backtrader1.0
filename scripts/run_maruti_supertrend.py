#!/usr/bin/env python3
# scripts/run_maruti_supertrend.py

import os
import sys
from datetime import datetime
import pandas as pd
import backtrader as bt

# ─── project root ─────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ───────────────────────────────────────────────────────────────────────────────

from data.load_candles     import load_candles
from strategies.supertrend import ST  # your SuperTrend indicator/strategy

# — your ST params ———————————————————————————————————————————————————————
ST_PARAMS = {
    "MARUTI": dict(period=20, mult=3.0),
}
SYMBOLS = list(ST_PARAMS.keys())

# — hard‑coded target date —————————————————————————————————————————————————
TARGET_DATE = "2025-07-17"
WARMUP      = "2025-04-01"

def normalize_dt(ds, is_start):
    return ds + (" 00:00:00" if is_start else " 23:59:59")

# ─── DEBUG SUBCLASS ────────────────────────────────────────────────────────────
class STDebug(ST):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def notify_order(self, order):
        dt   = self.data.datetime.datetime(0)
        name = order.getordername()
        if order.status in [order.Submitted, order.Accepted]:
            print(f"{dt}  ➤ ORDER {name} submitted/accepted")
        elif order.status is order.Completed:
            typ = "BUY" if order.isbuy() else "SELL"
            print(f"{dt}  ✓ ORDER {typ} executed size={order.executed.size} @ {order.executed.price:.2f}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            st = order.Status[order.status]
            print(f"{dt}  ✗ ORDER {name} {st}")

    def notify_trade(self, trade):
        if trade.isclosed:
            dt = self.data.datetime.datetime(0)
            print(f"{dt}  ⚡ TRADE closed — P&L Gross {trade.pnl:.2f} Net {trade.pnlcomm:.2f}")

    def next(self):
        # Only run the flip logic and its prints—no per-bar logging
        super().next()
# ────────────────────────────────────────────────────────────────────────────────

def run_period(symbol):
    # prepare timestamps
    start_full = normalize_dt(WARMUP, True)
    end_full   = normalize_dt(TARGET_DATE, False)

    # 1) load data
    df = load_candles(symbol, start_full, end_full)
    df.index = pd.to_datetime(df.index)
    print(f"\n{symbol}: total bars = {len(df)}")
    day = df.loc[TARGET_DATE]
    print(f"{symbol}: bars on {TARGET_DATE} = {len(day)}  (should be ≈375)\n")

    # 2) setup Cerebro
    cerebro = bt.Cerebro()
    cerebro.broker.set_coc(True)                   # execute orders on bar close
    cerebro.broker.setcash(500_000)                # ample cash
    cerebro.broker.setcommission(commission=0.0002)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    # 3) feed data
    data = bt.feeds.PandasData(
        dataname    = df,
        fromdate    = datetime.strptime(start_full, "%Y-%m-%d %H:%M:%S"),
        todate      = datetime.strptime(end_full,   "%Y-%m-%d %H:%M:%S"),
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1,
    )
    cerebro.adddata(data, name=symbol)

    # 4) add the debug strategy
    params = ST_PARAMS[symbol]
    cerebro.addstrategy(
        STDebug,
        st_period  = params["period"],
        st_mult    = params["mult"],
        eval_start = datetime.strptime(normalize_dt(TARGET_DATE, True), "%Y-%m-%d %H:%M:%S")
    )

    # 5) run
    strat = cerebro.run()[0]

    # 6) final summary
    tr   = strat.analyzers.trades.get_analysis()
    tot  = tr.get("total", {}).get("closed", 0)
    won  = tr.get("won",   {}).get("total", 0)
    lost = tr.get("lost",  {}).get("total", 0)
    winp = (won / tot * 100) if tot else 0.0

    print(f"\n--- SUMMARY for {symbol} on {TARGET_DATE} @ ST({params['period']},{params['mult']}) ---")
    print(f"Trades   : {tot}")
    print(f"Win Rate : {winp:.1f}% ({won}W/{lost}L)\n")

if __name__ == "__main__":
    for sym in SYMBOLS:
        run_period(sym)
