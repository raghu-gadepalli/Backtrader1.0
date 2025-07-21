#!/usr/bin/env python3
"""
scripts/run_backtest.py

Backtest SuperTrend for July 2025 with 1% SL & 0.5% TP,
dumping a single CSV of all closed trades (with PnL) plus a summary CSV.

Warm‑up/test split:
  • Warm‑up = last period*WARMUP_FACTOR bars before TEST_START
  • Test    = bars from TEST_START → END
"""

import os
import sys
import pandas as pd
from datetime import datetime

# ─── project root ────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


import backtrader as bt
from data.load_candles   import load_candles
from strategies.supertrend import ST as STBase

# ─── STRATEGY WITH INTERNAL ORDER LOG ────────────────────────────────────────
class STWithSLTP(STBase):
    """
    SuperTrend + fixed SL/TP + internal order logging.
    Orders are paired after the run to compute trades + PnL.
    """
    def __init__(self, *args, **kwargs):
        self.stop_loss_perc   = kwargs.pop("stop_loss_perc")
        self.take_profit_perc = kwargs.pop("take_profit_perc")
        super().__init__(*args, **kwargs)
        self._entry_price = None
        # collect every Completed order
        self.order_log = []

    def notify_order(self, order):
        super().notify_order(order)
        if order.status == order.Completed:
            dt    = self.data.datetime.datetime(0)
            price = order.executed.price
            size  = order.executed.size
            side  = "BUY" if order.isbuy() else "SELL"
            self.order_log.append({
                "symbol": self.data._name,
                "dt":      dt.strftime("%Y-%m-%d %H:%M:%S"),
                "side":    side,
                "price":   price,
                "size":    size,
            })
            # track for SL/TP
            self._entry_price = price

    def next(self):
        super().next()
        if not self.position or self._entry_price is None:
            return

        price = self.data.close[0]
        size  = self.position.size

        # LONG logic
        if size > 0:
            if price <= self._entry_price * (1 - self.stop_loss_perc):
                self.close(); self._entry_price = None
            elif price >= self._entry_price * (1 + self.take_profit_perc):
                self.close(); self._entry_price = None

        # SHORT logic
        elif size < 0:
            if price >= self._entry_price * (1 + self.stop_loss_perc):
                self.close(); self._entry_price = None
            elif price <= self._entry_price * (1 - self.take_profit_perc):
                self.close(); self._entry_price = None


# ─── BACKTEST PARAMETERS ─────────────────────────────────────────────────────
ST_PARAMS = {
    "ICICIBANK": dict(period=60, mult=9.0),
    "INFY":      dict(period=60, mult=14.0),
    "RELIANCE":  dict(period=60, mult=7.6),
}

STOP_LOSS_PCT   = 0.01    # 1%
TAKE_PROFIT_PCT = 0.0025   # 0.5%

BURN_IN_DATE   = "2025-02-15"
TEST_START     = "2025-07-01"
END            = "2025-07-17"
WARMUP_FACTOR  = 10      # bars = period * this

STARTING_CASH = 500_000
COMMISSION    = 0.0002

# ─── OUTPUT DIRECTORY ─────────────────────────────────────────────────────────
_ROOT       = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


# ─── CEREBRO SETUP ────────────────────────────────────────────────────────────
def make_cerebro():
    cb = bt.Cerebro(stdstats=False)
    cb.broker.set_coc(True)
    cb.broker.setcash(STARTING_CASH)
    cb.broker.setcommission(commission=COMMISSION)
    cb.addanalyzer(bt.analyzers.SharpeRatio,   _name="sharpe",
                   timeframe=bt.TimeFrame.Minutes, riskfreerate=0.0)
    cb.addanalyzer(bt.analyzers.DrawDown,      _name="drawdown")
    cb.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    return cb


# ─── MAIN BACKTEST LOOP ──────────────────────────────────────────────────────
all_trades = []
summary    = []

for symbol, params in ST_PARAMS.items():
    period, mult = params["period"], params["mult"]
    print(f"\n=== {symbol} | ST({period},{mult}) + SL {STOP_LOSS_PCT*100:.1f}% / TP {TAKE_PROFIT_PCT*100:.1f}% ===")

    # 1) load full history
    df_all = load_candles(symbol, BURN_IN_DATE, END)
    df_all.index = pd.to_datetime(df_all.index)

    # 2) split warm‑up vs test
    ts_dt       = datetime.strptime(TEST_START, "%Y-%m-%d")
    df_warm_all = df_all[df_all.index < ts_dt]
    df_test     = df_all[df_all.index >= ts_dt]

    needed = period * WARMUP_FACTOR
    if len(df_warm_all) < needed:
        print(f"❗ Not enough warm‑up for {symbol} ({len(df_warm_all)} < {needed}), aborting.")
        sys.exit(1)

    df_warm = df_warm_all.tail(needed)
    df      = pd.concat([df_warm, df_test])

    # 3) run Cerebro
    cerebro = make_cerebro()
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)
    cerebro.addstrategy(
        STWithSLTP,
        st_period=period,
        st_mult=mult,
        stop_loss_perc=STOP_LOSS_PCT,
        take_profit_perc=TAKE_PROFIT_PCT,
    )
    strat = cerebro.run()[0]

    # 4) summary metrics
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio",0.0) or 0.0
    dd     = strat.analyzers.drawdown.get_analysis().max.drawdown
    tr     = strat.analyzers.trades.get_analysis()
    won    = tr.get("won",{}).get("total",0)
    lost   = tr.get("lost",{}).get("total",0)
    tot    = tr.get("total",{}).get("closed",0)
    winr   = (won/tot*100) if tot else 0.0
    avg_w  = tr.get("won",{}).get("pnl",{}).get("average",0.0)
    avg_l  = tr.get("lost",{}).get("pnl",{}).get("average",0.0)
    expc   = (won/tot)*avg_w + (lost/tot)*avg_l if tot else float("nan")

    print(f"Sharpe: {sharpe:.2f}, Drawdown: {dd:.2f}%, "
          f"Trades: {tot}, Win%: {winr:.1f}%, Exp: {expc:.4f}")

    summary.append({
        "symbol":     symbol,
        "sharpe":     sharpe,
        "drawdown":   dd,
        "trades":     tot,
        "win_rate":   winr,
        "expectancy": expc,
    })

    # 5) pair orders into closed trades
    trades = []
    open_o = None
    for o in strat.order_log:
        if open_o is None:
            open_o = o
        else:
            # match opposite sides
            if (open_o["side"] == "BUY" and o["side"] == "SELL") or \
               (open_o["side"] == "SELL" and o["side"] == "BUY"):
                # compute PnL according to direction
                if open_o["side"] == "BUY":
                    pnl = (o["price"] - open_o["price"]) * open_o["size"]
                else:
                    pnl = (open_o["price"] - o["price"]) * abs(open_o["size"])
                trades.append({
                    "symbol":      symbol,
                    "entry_dt":    open_o["dt"],
                    "entry_price": open_o["price"],
                    "exit_dt":     o["dt"],
                    "exit_price":  o["price"],
                    "size":        open_o["size"],
                    "pnl":         pnl,
                })
                open_o = None
            else:
                # unexpected, skip
                open_o = o

    all_trades.extend(trades)

# 6) write trades CSV
df_trades  = pd.DataFrame(all_trades)
trades_out = os.path.join(RESULTS_DIR, "backtest_trades.csv")
df_trades.to_csv(trades_out, index=False)
print(f"\nWrote all trades → {trades_out}")

# 7) write summary CSV
df_sum      = pd.DataFrame(summary)
summary_out = os.path.join(RESULTS_DIR, "backtest_summary.csv")
df_sum.to_csv(summary_out, index=False)
print(f"Wrote summary  → {summary_out}")
