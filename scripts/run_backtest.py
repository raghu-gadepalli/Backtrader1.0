#!/usr/bin/env python3
# scripts/run_backtest.py
#
# Single strategy backtest (no sweep) with fixed BURN_IN_DATE warmup.
# - Feed warmup+test to Cerebro
# - Strategy ignores bars before the period start (ignore_before)
# - Filter TradeList rows to the slice
# - Recompute trades/win%/expectancy from filtered trades
# - Write summary & trade CSVs

import os
import sys
from datetime import datetime
import pandas as pd
import backtrader as bt

#  Project root 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

#  Imports 
from data.load_candles import load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy
from analyzers.trade_list import TradeList as TradeListAnalyzer  # required

#  GLOBAL CONFIG 
BURN_IN_DATE  = "2024-05-01 00:00:00"
STARTING_CASH = 500_000
COMMISSION    = 0.0002

SYMBOLS = ["TECHM"]
PERIODS = [
    ("Jul-25", "2025-07-01 09:15:00", "2025-07-22 15:30:00"),
]

# ---- ONE param set (tweak here) --------------------------------------------
PARAMS = dict(
    # fast=120,
    # mid1=320,
    # mid2=1200,
    # mid3=3800,

    fast=80,
    mid1=220,
    mid2=560,
    mid3=1520,

    adx_threshold=25.0,
    adx_period=14,
    atr_period=14,
    atr_mult=1.0,          # make sure this matches your strat default if used

    # Exit controls
    use_sl_tg=False,
    use_trailing=False,
    use_signal_exit=True,
    reentry_cooldown=0,
    ignore_before=None,    # will be overridden per period below

    # Legacy SL/TG fields (kept for CSV/logging; strat will ignore when OFF)
    sl_mode="OFF",
    sl_value=0.0,
    tg_mode="OFF",
    tg1=0.0,
    tg2=0.0,
    tg3=0.0,

    trail_type="NONE",
    trail_params=""
)

#  Helpers 
def make_cerebro():
    c = bt.Cerebro(stdstats=False)
    c.broker.set_coc(True)
    c.broker.setcash(STARTING_CASH)
    c.broker.setcommission(commission=COMMISSION)
    c.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                  timeframe=bt.TimeFrame.Days, riskfreerate=0.0)
    c.addanalyzer(bt.analyzers.DrawDown,    _name="ddown")
    c.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    c.addanalyzer(TradeListAnalyzer, _name="tlist")
    return c

def pandas_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high-low).abs(),
                    (high-prev_close).abs(),
                    (low-prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()

def safe_get(analyzers, name, field):
    try:
        val = getattr(analyzers.getbyname(name).get_analysis(), field)
        if isinstance(val, (list, tuple)) and val:
            return float(val[0])
        return float(val)
    except Exception:
        return None

def filter_for_strategy(params, strat_cls):
    allowed = set(strat_cls.params._getkeys())
    return {k: v for k, v in params.items() if k in allowed}

def recompute_trade_stats(trades):
    if not trades:
        return 0, 0.0, 0.0
    total = len(trades)
    pnls = [t.get("pnl", 0.0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_cnt = len(wins)
    win_rate = (win_cnt / total * 100.0) if total else 0.0
    avg_w = sum(wins)/win_cnt if win_cnt else 0.0
    loss_cnt = len(losses)
    avg_l = sum(losses)/loss_cnt if loss_cnt else 0.0
    expectancy = (avg_w * (win_cnt/total)) + (avg_l * (loss_cnt/total)) if total else 0.0
    return total, win_rate, expectancy

#  Core run 
def run_period(symbol, label, start_raw, end_raw, base_params):
    # Load warmup + test
    df_all = load_candles(symbol, BURN_IN_DATE, end_raw)
    if not hasattr(df_all, "index"):
        raise TypeError("load_candles returned non-DataFrame? Check import.")
    df_all.index = pd.to_datetime(df_all.index)

    ts_start = pd.to_datetime(start_raw)
    ts_end   = pd.to_datetime(end_raw)

    df_test = df_all[(df_all.index >= ts_start) & (df_all.index <= ts_end)].copy()
    if df_test.empty:
        print(f"[WARN] {symbol}/{label}: empty test slice.")
        return None, []

    atr_mean = float(pandas_atr(df_test, base_params.get("atr_period", 14)).mean())

    cerebro = make_cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=df_all), name=symbol)

    # Add ignore_before to prevent trades in warm-up inside strat
    params = dict(base_params)  # copy
    params["ignore_before"] = start_raw

    sp = filter_for_strategy(params, HmaMultiTrendStrategy)
    extra = set(params) - set(sp)
    if extra:
        print(f"[INFO] Ignoring params for strategy: {extra}")

    strat = cerebro.addstrategy(HmaMultiTrendStrategy, **sp)
    strat = cerebro.run()[0]

    sharpe = safe_get(strat.analyzers, "sharpe", "sharperatio")
    dd_pct = safe_get(strat.analyzers, "ddown",  "maxdrawdown") or 0.0

    # Filter trades to slice
    trade_rows = []
    for rec in strat.analyzers.tlist.get_analysis():
        dt_in = pd.to_datetime(rec["dt_in"])
        if ts_start <= dt_in <= ts_end:
            rec.update({
                "symbol": symbol,
                "period_label": label,
                "atr_mean": atr_mean,
                **{k: params.get(k) for k in (
                    "fast","mid1","mid2","mid3",
                    "sl_mode","sl_value","tg_mode","tg1","tg2","tg3",
                    "trail_type","use_sl_tg","use_trailing","use_signal_exit",
                    "reentry_cooldown"
                ) if k in params}
            })
            trade_rows.append(rec)

    total_trades, win_rate, expectancy = recompute_trade_stats(trade_rows)

    summary = dict(
        symbol=symbol, period_label=label,
        atr_mean=atr_mean,
        sharpe=sharpe if sharpe is not None else float("-inf"),
        drawdown=dd_pct/100.0,
        trades=total_trades,
        win_rate=win_rate,
        expectancy=expectancy,
        **params
    )
    return summary, trade_rows

#  Main 
def main():
    summaries = []
    trades_all = []

    for symbol in SYMBOLS:
        for (label, start_raw, end_raw) in PERIODS:
            s, t = run_period(symbol, label, start_raw, end_raw, PARAMS)
            if s:
                summaries.append(s)
                trades_all.extend(t)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sum_path   = os.path.join(RESULTS_DIR, f"backtest_summary_{ts}.csv")
    trade_path = os.path.join(RESULTS_DIR, f"backtest_trades_{ts}.csv")

    pd.DataFrame(summaries).to_csv(sum_path, index=False)

    if trades_all:
        df_tr = pd.DataFrame(trades_all)
        wanted = [
            "dt_in","dt_out","price_in","price_out","size","side",
            "pnl","pnl_comm","barlen","tradeid",
            "atr_entry","atr_pct","mae_abs","mae_pct",
            "mfe_abs","mfe_pct","ret_pct",
            "symbol","period_label",
            "fast","mid1","mid2","mid3",
            "sl_mode","sl_value","tg_mode","tg1","tg2","tg3","trail_type",
            "use_sl_tg","use_trailing","use_signal_exit","reentry_cooldown",
            "atr_mean"
        ]
        cols = [c for c in wanted if c in df_tr.columns]
        df_tr[cols].to_csv(trade_path, index=False)
    else:
        open(trade_path, "w").write("")

    print(f"\nWrote {sum_path}")
    print(f"Wrote {trade_path}")

if __name__ == "__main__":
    main()
