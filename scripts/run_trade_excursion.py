#!/usr/bin/env python3
"""
scripts/run_trade_excursion.py

Run SuperTrend for July 2025 (no SL/TP) and for each closed trade log:
  • entry_dt, entry_price
  • exit_dt, exit_price
  • max_price (highest high during the trade)
  • min_price (lowest low during the trade)
  • pnl

Outputs results/trade_excursions.csv for SL/TP analysis.
"""

import os
import sys
import pandas as pd
from datetime import datetime

# ─── project root ────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)
OUT_CSV     = os.path.join(RESULTS_DIR, "trade_excursions.csv")

import backtrader as bt
from data.load_candles     import load_candles
from strategies.supertrend import ST as STBase

# ─── STRATEGY WITH ORDER LOGGING ─────────────────────────────────────────────
class STLogger(STBase):
    """
    SuperTrend entry/exit only; logs every Completed order into self.order_log.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_log = []

    def notify_order(self, order):
        super().notify_order(order)
        if order.status == order.Completed:
            dt    = self.data.datetime.datetime(0)
            self.order_log.append({
                "symbol": self.data._name,
                "dt":      dt.strftime("%Y-%m-%d %H:%M:%S"),
                "side":    "BUY" if order.isbuy() else "SELL",
                "price":   order.executed.price,
                "size":    order.executed.size,
            })


# ─── BACKTEST PARAMETERS ─────────────────────────────────────────────────────
ST_PARAMS = {
    "ICICIBANK": dict(period=60, mult=9.0),
    "INFY":      dict(period=60, mult=14.0),
    "RELIANCE":  dict(period=60, mult=7.6),
}

BURN_IN_DATE   = "2025-02-15"
TEST_START     = "2025-07-01"
END            = "2025-07-17"
WARMUP_FACTOR  = 10   # warm‑up bars = period * this

STARTING_CASH = 500_000
COMMISSION    = 0.0002


# ─── CEREBRO SETUP ────────────────────────────────────────────────────────────
def make_cerebro():
    cb = bt.Cerebro(stdstats=False)
    cb.broker.set_coc(True)
    cb.broker.setcash(STARTING_CASH)
    cb.broker.setcommission(commission=COMMISSION)
    # we only need TradeAnalyzer for counts if you like, but it's optional
    cb.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    return cb


# ─── MAIN LOOP & EXCURSION CALCULATION ───────────────────────────────────────
all_excursions = []

for symbol, params in ST_PARAMS.items():
    period, mult = params["period"], params["mult"]
    print(f"\n→ Running {symbol} @ ST({period},{mult}), no SL/TP")

    # 1) load full history
    df_all = load_candles(symbol, BURN_IN_DATE, END)
    df_all.index = pd.to_datetime(df_all.index)

    # 2) split warm‑up vs test
    ts_dt       = datetime.strptime(TEST_START, "%Y-%m-%d")
    df_warm_all = df_all[df_all.index < ts_dt]
    df_test     = df_all[df_all.index >= ts_dt]

    needed = period * WARMUP_FACTOR
    if len(df_warm_all) < needed:
        print(f"  ⚠️  Not enough warm‑up bars ({len(df_warm_all)} < {needed}), skipping.")
        continue

    df_warm = df_warm_all.tail(needed)
    df      = pd.concat([df_warm, df_test])

    # 3) run Cerebro
    cerebro = make_cerebro()
    data = bt.feeds.PandasData(
        dataname    = df,
        timeframe   = bt.TimeFrame.Minutes,
        compression = 1,
    )
    cerebro.adddata(data, name=symbol)
    cerebro.addstrategy(
        STLogger,
        st_period=period,
        st_mult=mult,
    )
    strat = cerebro.run()[0]

    # 4) pair orders into trades and compute excursion
    trades = []
    open_o = None
    for o in strat.order_log:
        if open_o is None:
            open_o = o
        else:
            # entry BUY → exit SELL, or entry SELL → exit BUY
            if (open_o["side"] == "BUY" and o["side"] == "SELL") or \
               (open_o["side"] == "SELL" and o["side"] == "BUY"):
                # slice the DataFrame between entry & exit
                dt_in  = datetime.strptime(open_o["dt"], "%Y-%m-%d %H:%M:%S")
                dt_out = datetime.strptime(o["dt"],       "%Y-%m-%d %H:%M:%S")
                df_trade = df[(df.index >= dt_in) & (df.index <= dt_out)]
                max_price = df_trade["high"].max()
                min_price = df_trade["low"].min()

                # compute PnL
                if open_o["side"] == "BUY":
                    pnl = o["price"] - open_o["price"]
                else:
                    pnl = open_o["price"] - o["price"]

                trades.append({
                    "symbol":      symbol,
                    "entry_dt":    open_o["dt"],
                    "entry_price": open_o["price"],
                    "exit_dt":     o["dt"],
                    "exit_price":  o["price"],
                    "max_price":   max_price,
                    "min_price":   min_price,
                    "pnl":         pnl,
                })
                open_o = None
            else:
                # mis‑matched sequence: reset
                open_o = o

    print(f"  → {len(trades)} closed trades for {symbol}")
    all_excursions.extend(trades)

# debug
print(f"\nTotal excursions collected: {len(all_excursions)}")

# 5) write CSV
pd.DataFrame(all_excursions).to_csv(OUT_CSV, index=False)
print(f"Wrote trade excursions → {OUT_CSV}")
