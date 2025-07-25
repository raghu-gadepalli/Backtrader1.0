#!/usr/bin/env python3
# scripts/run_hmamulti_sweep.py
#
# 3PASS COARSEREFINE SWEEP (fast+mid1  mid2  mid3) ACROSS PERIODS
# - Warmup bars = max(periods) * WARMUP_FACTOR; skip combo if insufficient data
# - Cerebro gets (warmup + test); metrics/ATR mean computed on test slice only
# - Outputs:
#     results/hmamulti_sweep_results.csv   (ALL rows, every stage & period)
#     results/hmamulti_sweep_trades.csv    (per-trade rows via TradeList analyzer)

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
    sys.path.insert(1, _ROOT)

RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

#  Imports (match your tree) 
from data.load_candles import load_candles
from strategies.hma_multitrend import HmaMultiTrendStrategy
from analyzers.trade_list import TradeList as TradeListAnalyzer  # required

#  USER SETTINGS 
SYMBOLS = ["ICICIBANK", "INFY", "RELIANCE"]

# Period windows (label, start, end)
PERIODS = [
    # ("Jan-25", "2025-01-01 09:15:00", "2025-01-31 15:30:00"),
    # ("Feb-25", "2025-02-01 09:15:00", "2025-02-28 15:30:00"),
    # ("Mar-25", "2025-03-01 09:15:00", "2025-03-31 15:30:00"),
    # ("Apr-25", "2025-04-01 09:15:00", "2025-04-30 15:30:00"),
    # ("May-25", "2025-05-01 09:15:00", "2025-05-31 15:30:00"),
    # ("Jun-25", "2025-06-01 09:15:00", "2025-06-30 15:30:00"),
    ("Jul-25", "2025-07-01 09:15:00", "2025-07-22 15:30:00"),
]

STARTING_CASH = 500_000
COMMISSION    = 0.0002

# Warmup handling
WARMUP_FACTOR = 10
BAR_MINUTES   = 1

# PASS RANGES  (ensure f < m1 < m2 < m3)
FAST_PERIODS =  range(60, 181, 30)        # Pass 1
MID1_PERIODS =  range(180, 721, 60)       # Pass 1
MID2_PERIODS =  [600, 900, 1200, 1800]    # Pass 2
MID3_PERIODS =  [1800, 2400, 3200, 3800]  # Pass 3

# Survivors per pass
PASS1_N = 5
PASS2_N = 5
PASS3_N = 5

# Enforce uniqueness on the dimension optimized in that pass
DISTINCT1 = True   # unique 'fast' in pass1
DISTINCT2 = True   # unique 'mid2' in pass2
DISTINCT3 = True   # unique 'mid3' in pass3

PRIMARY_METRIC = "sharpe_mean"  # or "expectancy_mean"

# ATR params to feed & log
ATR_PERIOD = 14
ATR_MULT   = 0.0

#  Helpers 
def make_cerebro():
    c = bt.Cerebro(stdstats=False)
    c.broker.set_coc(True)
    c.broker.setcash(STARTING_CASH)
    c.broker.setcommission(commission=COMMISSION)
    c.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                  timeframe=bt.TimeFrame.Days, riskfreerate=0.0)
    c.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    c.addanalyzer(bt.analyzers.DrawDown, _name="ddown")
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

def sort_key(rec):
    # Higher PRIMARY_METRIC first; then expectancy_mean; then trades_sum
    return (-rec[PRIMARY_METRIC], -rec["expectancy_mean"], -rec["trades_sum"])

#  Single-period run 
def run_period(symbol, label, start_raw, end_raw, f, m1, m2, m3, warmup_bars):
    test_start_ts = pd.to_datetime(start_raw)
    test_end_ts   = pd.to_datetime(end_raw)

    warmup_start_ts = test_start_ts - timedelta(minutes=warmup_bars * BAR_MINUTES)

    df_all = load_candles(
        symbol,
        warmup_start_ts.strftime("%Y-%m-%d %H:%M:%S"),
        test_end_ts.strftime("%Y-%m-%d %H:%M:%S")
    )
    df_all.index = pd.to_datetime(df_all.index)

    if df_all.empty or len(df_all) < warmup_bars:
        return None, []

    df_test = df_all[(df_all.index >= test_start_ts) & (df_all.index <= test_end_ts)].copy()
    if df_test.empty:
        return None, []

    atr_series = pandas_atr(df_test, ATR_PERIOD)
    atr_mean   = float(atr_series.mean())

    cerebro = make_cerebro()
    data = bt.feeds.PandasData(dataname=df_all,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data)

    strat_kwargs = dict(
        fast=f, mid1=m1, mid2=m2, mid3=m3,
        atr_period=ATR_PERIOD, atr_mult=ATR_MULT,
        printlog=False
    )
    # If strategy supports prewarm_bars, you can add it here:
    # strat_kwargs["prewarm_bars"] = warmup_bars

    strat = cerebro.addstrategy(HmaMultiTrendStrategy, **strat_kwargs)
    strat = cerebro.run()[0]

    sharpe = safe_get(strat.analyzers, "sharpe", "sharperatio")
    dd_pct = safe_get(strat.analyzers, "ddown", "maxdrawdown") or 0.0
    td     = strat.analyzers.trades.get_analysis()

    total  = td.get("total", {}).get("closed", 0) or 0
    won    = td.get("won",   {}).get("total", 0) or 0
    win_rt = (won / total * 100.0) if total else 0.0
    expct  = compute_expectancy(td)

    trades_list = []
    for rec in strat.analyzers.tlist.get_analysis():
        rec.update({
            "symbol": symbol, "period_label": label,
            "fast": f, "mid1": m1, "mid2": m2, "mid3": m3,
            "atr_period": ATR_PERIOD, "atr_mult": ATR_MULT,
            "atr_mean": atr_mean
        })
        trades_list.append(rec)

    summary = dict(
        symbol=symbol, period_label=label,
        fast=f, mid1=m1, mid2=m2, mid3=m3,
        atr_period=ATR_PERIOD, atr_mult=ATR_MULT, atr_mean=atr_mean,
        sharpe=sharpe if sharpe is not None else float("-inf"),
        expectancy=expct,
        trades=total,
        win_rate=win_rt,
        drawdown=dd_pct/100.0
    )
    return summary, trades_list

#  Aggregate a combo across all periods 
def eval_combo(symbol, f, m1, m2, m3, stage, writer, trade_collector):
    max_len     = max(f, m1, m2, m3, ATR_PERIOD)
    warmup_bars = max_len * WARMUP_FACTOR

    sharpe_vals, exp_vals, trade_vals = [], [], []

    for (label, start_raw, end_raw) in PERIODS:
        row, trades = run_period(symbol, label, start_raw, end_raw,
                                 f, m1, m2, m3, warmup_bars)
        if row is None:
            continue

        r = row.copy()
        r["stage"] = stage
        writer.writerow(r)

        sharpe_vals.append(row["sharpe"])
        exp_vals.append(row["expectancy"])
        trade_vals.append(row["trades"])

        trade_collector.extend(trades)

    if not sharpe_vals:
        return None

    return dict(
        symbol=symbol, fast=f, mid1=m1, mid2=m2, mid3=m3,
        atr_period=ATR_PERIOD, atr_mult=ATR_MULT,
        sharpe_mean=sum(sharpe_vals)/len(sharpe_vals),
        expectancy_mean=sum(exp_vals)/len(exp_vals),
        trades_sum=sum(trade_vals)
    )

#  Main 
def main():
    res_path    = os.path.join(RESULTS_DIR, "hmamulti_sweep_results.csv")
    trades_path = os.path.join(RESULTS_DIR, "hmamulti_sweep_trades.csv")

    res_fields = ["symbol","period_label","stage",
                  "fast","mid1","mid2","mid3",
                  "atr_period","atr_mult","atr_mean",
                  "sharpe","expectancy","trades","win_rate","drawdown"]

    tr_fields  = [
        "dt_in","dt_out","price_in","price_out","size","side",
        "pnl","pnl_comm","barlen","tradeid",
        "atr_entry","atr_pct","mae_abs","mae_pct",
        "mfe_abs","mfe_pct","ret_pct",
        "symbol","period_label",
        "fast","mid1","mid2","mid3",
        "atr_period","atr_mult","atr_mean"
    ]

    trade_rows_all = []

    with open(res_path, "w", newline="") as rf:
        rw_all = csv.DictWriter(rf, fieldnames=res_fields)
        rw_all.writeheader()

        # PASS 1: fast & mid1
        print("\n=== PASS 1: fast & mid1 ===")
        p1_results = []
        combos_p1 = [(f, m1) for f in FAST_PERIODS for m1 in MID1_PERIODS if f < m1]
        total_p1 = len(SYMBOLS) * len(combos_p1)
        done = 0
        for symbol in SYMBOLS:
            for f, m1 in combos_p1:
                done += 1
                # cheap placeholders for mid2/mid3
                def_m2, def_m3 = f * 2, f * 4
                agg = eval_combo(symbol, f, m1, def_m2, def_m3, stage=1,
                                 writer=rw_all,
                                 trade_collector=trade_rows_all)
                if agg:
                    p1_results.append(agg)
                print(f"[P1 {done}/{total_p1}] {symbol} f={f} m1={m1}")
        p1_results.sort(key=sort_key)

        heads1, seen_fast = [], set()
        for r in p1_results:
            if DISTINCT1 and r["fast"] in seen_fast:
                continue
            heads1.append(r)
            seen_fast.add(r["fast"])
            if len(heads1) >= PASS1_N:
                break

        # PASS 2: mid2
        print("\n=== PASS 2: mid2 ===")
        p2_results = []
        combos_p2 = []
        for h in heads1:
            f, m1 = h["fast"], h["mid1"]
            combos_p2 += [(symbol, f, m1, m2) for symbol in SYMBOLS
                          for m2 in MID2_PERIODS if m2 > m1]

        total_p2 = len(combos_p2)
        done = 0
        for symbol, f, m1, m2 in combos_p2:
            done += 1
            def_m3 = f * 4
            agg = eval_combo(symbol, f, m1, m2, def_m3, stage=2,
                             writer=rw_all,
                             trade_collector=trade_rows_all)
            if agg:
                p2_results.append(agg)
            print(f"[P2 {done}/{total_p2}] {symbol} f={f} m1={m1} m2={m2}")
        p2_results.sort(key=sort_key)

        heads2, seen_m2 = [], set()
        for r in p2_results:
            if DISTINCT2 and r["mid2"] in seen_m2:
                continue
            heads2.append(r)
            seen_m2.add(r["mid2"])
            if len(heads2) >= PASS2_N:
                break

        # PASS 3: mid3
        print("\n=== PASS 3: mid3 ===")
        p3_results = []
        combos_p3 = []
        for h in heads2:
            f, m1, m2 = h["fast"], h["mid1"], h["mid2"]
            combos_p3 += [(symbol, f, m1, m2, m3) for symbol in SYMBOLS
                          for m3 in MID3_PERIODS if m3 > m2]

        total_p3 = len(combos_p3)
        done = 0
        for symbol, f, m1, m2, m3 in combos_p3:
            done += 1
            agg = eval_combo(symbol, f, m1, m2, m3, stage=3,
                             writer=rw_all,
                             trade_collector=trade_rows_all)
            if agg:
                p3_results.append(agg)
            print(f"[P3 {done}/{total_p3}] {symbol} f={f} m1={m1} m2={m2} m3={m3}")
        p3_results.sort(key=sort_key)

        heads3, seen_m3 = [], set()
        for r in p3_results:
            if DISTINCT3 and r["mid3"] in seen_m3:
                continue
            heads3.append(r)
            seen_m3.add(r["mid3"])
            if len(heads3) >= PASS3_N:
                break

    # Write trades file
    df_tr = pd.DataFrame(trade_rows_all)
    if not df_tr.empty:
        cols = [c for c in tr_fields if c in df_tr.columns]
        df_tr[cols].to_csv(trades_path, index=False)
    else:
        open(trades_path, "w").write("")

    print(f"\nWrote {res_path}")
    print(f"Wrote {trades_path}")
    print("\nTop picks (pass3 survivors):")
    for r in heads3:
        print(r)

if __name__ == "__main__":
    main()
