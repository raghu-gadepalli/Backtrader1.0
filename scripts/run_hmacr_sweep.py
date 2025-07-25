#!/usr/bin/env python3
# scripts/run_hmacr_sweep.py
#
# Flat grid sweep for HMA crossover (fast / slow) across multiple periods.
# - Warmup bars = max(fast, slow, ATR_PERIOD) * WARMUP_FACTOR
# - Skip combo if data < warmup bars
# - Feed warmup+test to Cerebro; compute metrics & ATR mean on test slice only
# - Outputs:
#     results/hmacr_sweep_results.csv
#     results/hmacr_sweep_trades.csv   (if TradeList analyzer is available)

import os
import sys
import csv
from itertools import product
from datetime import timedelta
import pandas as pd
import backtrader as bt

#  Project root 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

#  Imports (adjust paths if needed) 
from data.load_candles import load_candles
from strategies.hma_crossover import HmaCrossover
try:
    from analyzers.trade_list import TradeList as TradeListAnalyzer
    _HAS_TLIST = True
except Exception:
    _HAS_TLIST = False

#  USER CONFIG 
STOCKS = ["AXISBANK"]
# STOCKS = ["AXISBANK", "HDFCBANK"]

# Period windows (label, start, end)
PERIODS = [
    ("Apr-25", "2025-04-01 09:15:00", "2025-04-30 15:30:00"),
    ("May-25", "2025-05-01 09:15:00", "2025-05-31 15:30:00"),
    ("Jun-25", "2025-06-01 09:15:00", "2025-06-30 15:30:00"),
    ("Jul-25", "2025-07-01 09:15:00", "2025-07-06 15:30:00"),  # keep your original end
]

STARTING_CASH = 500_000
COMMISSION    = 0.0002

# Warmup
WARMUP_FACTOR = 10
BAR_MINUTES   = 1

# ATR (if your strategy ignores, still logged)
ATR_PERIOD = 14
ATR_MULT   = 0.0

# Grids
FAST_VALS = list(range(40, 1001, 40))
SLOW_VALS = list(range(80, 3001, 80))

# Outputs
RES_PATH    = os.path.join(RESULTS_DIR, "hmacr_sweep_results.csv")
TRADES_PATH = os.path.join(RESULTS_DIR, "hmacr_sweep_trades.csv")

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
    if _HAS_TLIST:
        c.addanalyzer(TradeListAnalyzer, _name="tlist")
    return c

def pandas_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()

def safe_get(analyzers, name, field):
    try:
        val = getattr(analyzers.getbyname(name).get_analysis(), field)
        if isinstance(val, (list, tuple)) and val:
            return float(val[0])
        return float(val)
    except Exception:
        return None

def compute_expectancy(tstats: dict) -> float:
    try:
        won  = tstats.get("won", {})
        lost = tstats.get("lost", {})
        tot  = (won.get("total", 0) or 0) + (lost.get("total", 0) or 0)
        if not tot:
            return 0.0
        avg_w = won.get("pnl", {}).get("average", 0.0)
        avg_l = lost.get("pnl", {}).get("average", 0.0)
        win_p = (won.get("total", 0) or 0) / tot
        loss_p= (lost.get("total", 0) or 0) / tot
        return (avg_w * win_p) + (avg_l * loss_p)
    except Exception:
        return 0.0

#  Single-period run 
def run_period(symbol, label, start_raw, end_raw, fast, slow, warmup_bars):
    ts_start = pd.to_datetime(start_raw)
    ts_end   = pd.to_datetime(end_raw)
    warmup_start = ts_start - timedelta(minutes=warmup_bars * BAR_MINUTES)

    df_all = load_candles(
        symbol,
        warmup_start.strftime("%Y-%m-%d %H:%M:%S"),
        ts_end.strftime("%Y-%m-%d %H:%M:%S")
    )
    df_all.index = pd.to_datetime(df_all.index)

    if df_all.empty or len(df_all) < warmup_bars:
        return None, []

    df_test = df_all[(df_all.index >= ts_start) & (df_all.index <= ts_end)].copy()
    if df_test.empty:
        return None, []

    atr_mean = float(pandas_atr(df_test, ATR_PERIOD).mean())

    cerebro = make_cerebro()
    data = bt.feeds.PandasData(dataname=df_all,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data, name=symbol)

    strat_kwargs = dict(
        fast=fast,
        slow=slow,
        atr_mult=ATR_MULT,
        atr_period=ATR_PERIOD,
        printlog=False
    )
    # strat_kwargs["prewarm_bars"] = warmup_bars  # if supported

    cerebro.addstrategy(HmaCrossover, **strat_kwargs)
    strat = cerebro.run()[0]

    sharpe = safe_get(strat.analyzers, "sharpe", "sharperatio")
    dd_pct = safe_get(strat.analyzers, "ddown", "maxdrawdown") or 0.0
    td     = strat.analyzers.trades.get_analysis()

    total_trades = td.get("total", {}).get("closed", 0) or 0
    won          = td.get("won",   {}).get("total", 0) or 0
    win_rate     = (won / total_trades * 100.0) if total_trades else 0.0
    expectancy   = compute_expectancy(td)

    trades_list = []
    if _HAS_TLIST:
        for rec in strat.analyzers.tlist.get_analysis():
            rec.update({
                "symbol": symbol, "period_label": label,
                "fast": fast, "slow": slow,
                "atr_period": ATR_PERIOD, "atr_mult": ATR_MULT,
                "atr_mean": atr_mean
            })
            trades_list.append(rec)

    result = dict(
        symbol=symbol, period_label=label,
        fast=fast, slow=slow,
        atr_period=ATR_PERIOD, atr_mult=ATR_MULT, atr_mean=atr_mean,
        sharpe=sharpe if sharpe is not None else float("-inf"),
        expectancy=expectancy,
        trades=total_trades,
        win_rate=win_rate,
        drawdown=dd_pct/100.0
    )
    return result, trades_list

#  Main 
def main():
    # Prepare CSVs
    res_fields = ["symbol","period_label",
                  "fast","slow",
                  "atr_period","atr_mult","atr_mean",
                  "sharpe","expectancy","trades","win_rate","drawdown"]

    tr_fields  = [
        "dt_in","dt_out","price_in","price_out","size","side",
        "pnl","pnl_comm","barlen","tradeid",
        "atr_entry","atr_pct","mae_abs","mae_pct",
        "mfe_abs","mfe_pct","ret_pct",
        "symbol","period_label",
        "fast","slow",
        "atr_period","atr_mult","atr_mean"
    ]

    trade_rows_all = []

    with open(RES_PATH, "w", newline="") as rf:
        rw = csv.DictWriter(rf, fieldnames=res_fields)
        rw.writeheader()

        total = sum(1 for _s in STOCKS
                      for _ in PERIODS
                      for f, s in product(FAST_VALS, SLOW_VALS)
                      if f < s)
        done = 0

        for symbol in STOCKS:
            for (label, start_raw, end_raw) in PERIODS:
                for fast, slow in product(FAST_VALS, SLOW_VALS):
                    if fast >= slow:
                        continue

                    done += 1
                    warmup_bars = max(fast, slow, ATR_PERIOD) * WARMUP_FACTOR
                    res, trlist = run_period(symbol, label, start_raw, end_raw,
                                             fast, slow, warmup_bars)
                    if res is None:
                        continue

                    rw.writerow(res)
                    rf.flush()
                    trade_rows_all.extend(trlist)

                    print(f"[{done}/{total}] {symbol}/{label} f={fast} s={slow} "
                          f"SR={res['sharpe']:.3f} Exp={res['expectancy']:.2f}")

    # Trades CSV
    if trade_rows_all:
        df_tr = pd.DataFrame(trade_rows_all)
        cols = [c for c in tr_fields if c in df_tr.columns]
        df_tr[cols].to_csv(TRADES_PATH, index=False)
    else:
        open(TRADES_PATH, "w").write("")

    print(f"\nWrote {RES_PATH}")
    print(f"Wrote {TRADES_PATH}")

if __name__ == "__main__":
    main()
