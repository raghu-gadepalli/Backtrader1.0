#!/usr/bin/env python3
# scripts/kite_backtest.py

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
from data.load_candles_kite import load_candles_kite as load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy
from analyzers.trade_list import TradeList as TradeListAnalyzer

#  GLOBAL CONFIG 
BURN_IN_DATE  = "2025-06-15 00:00:00"    # fixed warmup start
STARTING_CASH = 500_000
COMMISSION    = 0.0002

#  SYMBOLS & PERIODS 
# Hardcode your list of (symbol, instrument_token) here:
SYMBOLS = [
    ("TECHM",    3465729),
    # ("RELIANCE", 738561),
    # ("INFY",     408065),
    # add more
]

# One or more test periods: (label, start, end)
PERIODS = [
    ("Jul-25", "2025-07-01 09:15:00", "2025-07-22 15:30:00"),
]

#  STRATEGY PARAMETERS (tweak as desired) 
PARAMS = dict(
    fast=80, mid1=220, mid2=560, mid3=1520,
    adx_threshold=25.0, adx_period=14,
    atr_period=14, atr_mult=1.0,
    use_sl_tg=False, use_trailing=False,
    use_signal_exit=True, reentry_cooldown=0,
    ignore_before=None,
    sl_mode="OFF", sl_value=0.0,
    tg_mode="OFF", tg1=0.0, tg2=0.0, tg3=0.0,
    trail_type="NONE", trail_params="",
)

#  HELPERS 
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
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()

def safe_get(analyzers, name, field):
    try:
        v = getattr(analyzers.getbyname(name).get_analysis(), field)
        return float(v[0] if isinstance(v, (list,tuple)) else v)
    except:
        return None

def filter_for_strategy(params, strat_cls):
    allowed = set(strat_cls.params._getkeys())
    return {k:v for k,v in params.items() if k in allowed}

def recompute_trade_stats(trades):
    if not trades:
        return 0, 0.0, 0.0
    pnls = [t.get("pnl",0.0) for t in trades]
    wins   = [p for p in pnls if p>0]
    losses = [p for p in pnls if p<=0]
    total  = len(pnls)
    win_rate = (len(wins)/total*100) if total else 0.0
    avg_w    = (sum(wins)/len(wins))   if wins else 0.0
    avg_l    = (sum(losses)/len(losses)) if losses else 0.0
    expectancy = (avg_w*(len(wins)/total) + avg_l*(len(losses)/total)) if total else 0.0
    return total, win_rate, expectancy

#  RUN ONE SYMBOL/PERIOD 
def run_period(symbol, token, start_raw, end_raw, base_params):
    # 1) Fetch warmup + test candles at 1min
    df_all = load_candles(symbol, token, BURN_IN_DATE, end_raw, frequency="1min")
    df_all.index = pd.to_datetime(df_all.index)

    ts_start = pd.to_datetime(start_raw)
    ts_end   = pd.to_datetime(end_raw)
    df_test  = df_all[(df_all.index >= ts_start) & (df_all.index <= ts_end)]
    if df_test.empty:
        print(f"[WARN] {symbol}: no data in {start_raw}{end_raw}")
        return None, []

    # 2) Precompute ATR mean
    atr_mean = float(pandas_atr(df_test, base_params["atr_period"]).mean())

    # 3) Set up backtrader
    cerebro = make_cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=df_all), name=symbol)

    # 4) Strategy params (including ignore_before)
    params = dict(base_params, ignore_before=start_raw)
    sp = filter_for_strategy(params, HmaMultiTrendStrategy)
    extra = set(params) - set(sp)
    if extra:
        print(f"[INFO] Ignoring strat params: {extra}")

    strat = cerebro.addstrategy(HmaMultiTrendStrategy, **sp)
    strat = cerebro.run()[0]

    # 5) Pull analyzers
    sharpe = safe_get(strat.analyzers, "sharpe",   "sharperatio") or float("-inf")
    dd_pct = (safe_get(strat.analyzers, "ddown",   "maxdrawdown") or 0.0) / 100.0

    # 6) Collect inperiod trades
    rows = []
    for rec in strat.analyzers.tlist.get_analysis():
        dt_in = pd.to_datetime(rec["dt_in"])
        if ts_start <= dt_in <= ts_end:
            rec.update({
                "symbol":    symbol,
                "atr_mean":  atr_mean,
                **{k:params[k] for k in (
                    "fast","mid1","mid2","mid3","atr_mult",
                    "sl_mode","sl_value","tg_mode","tg1","tg2","tg3",
                    "trail_type","use_sl_tg","use_trailing","use_signal_exit",
                    "reentry_cooldown"
                ) if k in params}
            })
            rows.append(rec)

    total, win_rate, expectancy = recompute_trade_stats(rows)

    summary = dict(
        symbol=symbol,
        atr_mean=atr_mean,
        sharpe=sharpe,
        drawdown=dd_pct,
        trades=total,
        win_rate=win_rate,
        expectancy=expectancy,
        **{k:params[k] for k in ("fast","mid1","mid2","mid3","atr_mult")}
    )
    return summary, rows

#  MAIN 
def main():
    summaries  = []
    trades_all = []

    for symbol, token in SYMBOLS:
        for start_raw, end_raw in [(p[1], p[2]) for p in PERIODS]:
            s, trs = run_period(symbol, token, start_raw, end_raw, PARAMS)
            if s:
                summaries.append(s)
                trades_all.extend(trs)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sum_path   = os.path.join(RESULTS_DIR, f"kite_backtest_summary_{ts}.csv")
    trade_path = os.path.join(RESULTS_DIR, f"kite_backtest_trades_{ts}.csv")

    pd.DataFrame(summaries).to_csv(sum_path,   index=False)
    pd.DataFrame(trades_all).to_csv(trade_path, index=False)

    print(f"\nWrote {sum_path}")
    print(f"Wrote {trade_path}")

if __name__ == "__main__":
    main()
