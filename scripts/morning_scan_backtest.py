#!/usr/bin/env python3
# scripts/morning_scan_backtest.py

import os
import sys
from datetime import datetime, timedelta
import pandas as pd
import backtrader as bt

# Project root
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Imports
from data.load_candles_kite import load_candles_kite as load_candles
from data.get_symbols     import fetch_symbols
from strategies.hma_multitrend import HmaMultiTrendStrategy
from analyzers.trade_list    import TradeList as TradeListAnalyzer

# CONFIG
RUN_DATE    = datetime.strptime("2025-07-23", "%Y-%m-%d")
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

PARAMS = dict(
    # fast=80, mid1=220, mid2=560, mid3=1520,
    fast=80, mid1=320, mid2=1200, mid3=3800,
    adx_threshold=20.0, adx_period=14,
    atr_period=14, atr_mult=1.0,
    use_sl_tg=True, use_trailing=False,
    use_signal_exit=True, reentry_cooldown=0, ignore_before=None,
    sl_mode="PCT", sl_value=0.5,
    # profit targets
    tg_mode="OFF", tg1=0.0, tg2=0.0, tg3=0.0,
    # legacy trailing
    trail_type="ATR_STEP", trail_params="mult=3.0",
)

# Legacy trail parsing
tmp = PARAMS.pop("trail_type", None)
tmp2 = PARAMS.pop("trail_params", None)
if tmp == "ATR_STEP":
    try:
        PARAMS["trail_atr_mult"] = float(tmp2.split("=", 1)[1])
    except:
        PARAMS["trail_atr_mult"] = 1.0

def pandas_atr(df, period=14):
    high, low, close = df.high, df.low, df.close
    prev = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev).abs(),
        (low  - prev).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()

def filter_for_strategy(params, strat_cls):
    allowed = set(strat_cls.params._getkeys())
    return {k: v for k, v in params.items() if k in allowed}

def recompute_trade_stats(trades):
    if not trades:
        return 0, 0.0, 0.0
    pnls = [t.get("pnl", 0.0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total = len(pnls)
    win_rate = (len(wins) / total * 100) if total else 0.0
    avg_w = sum(wins) / len(wins) if wins else 0.0
    avg_l = sum(losses) / len(losses) if losses else 0.0
    expectancy = avg_w * (len(wins) / total) + avg_l * (len(losses) / total)
    return total, win_rate, expectancy

def make_cerebro():
    c = bt.Cerebro(stdstats=False)
    c.broker.set_coc(True)
    c.broker.setcash(500_000)
    c.broker.setcommission(commission=0.0002)
    c.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                  timeframe=bt.TimeFrame.Days, riskfreerate=0.0)
    c.addanalyzer(bt.analyzers.DrawDown, _name="ddown")
    c.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    c.addanalyzer(TradeListAnalyzer, _name="tlist")
    return c

def in_window_or_open(rec, start, end):
    dt_in = rec.get("dt_in")
    if not dt_in:
        return False
    dt_in = pd.to_datetime(dt_in)
    if not (start <= dt_in <= end):
        return False
    dt_out = rec.get("dt_out")
    if not dt_out:
        return True
    dt_out = pd.to_datetime(dt_out)
    return dt_out <= end

def run_backtest_for(symbol, token, burn_in, start_raw, end_raw, base_params):
    # 1) Load data and slice for test window
    df_all = load_candles(symbol, token, burn_in, end_raw)
    df_all.index = pd.to_datetime(df_all.index)
    ts_start, ts_end = pd.to_datetime(start_raw), pd.to_datetime(end_raw)
    df_test = df_all.loc[ts_start:ts_end]
    if df_test.empty:
        return None, []

    # 2) ATR mean over test
    atr_mean = float(pandas_atr(df_test, base_params["atr_period"]).mean())

    # 3) Setup and run Cerebro
    cerebro = make_cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=df_all), name=symbol)
    strat_params = filter_for_strategy({**base_params, "ignore_before": start_raw}, HmaMultiTrendStrategy)
    extra = set(base_params) - set(strat_params)
    if extra:
        print(f"[INFO] ignoring strat params: {extra}")
    cerebro.addstrategy(HmaMultiTrendStrategy, **strat_params)
    strat = cerebro.run()[0]

    # 4) Analyzer metrics
    sharpe    = strat.analyzers.sharpe.get_analysis().get("sharperatio", None)
    ddown_pct = strat.analyzers.ddown.get_analysis().max.drawdown / 100.0

    # 5) Collect + filter trades
    all_trades = strat.analyzers.tlist.get_analysis()

    trades = [r for r in all_trades if in_window_or_open(r, ts_start, ts_end)]

    # 6) Stamp ATR mean on each trade record
    for rec in trades:
        rec["atr_mean"] = atr_mean

    # 7) Summary on closed trades
    closed = [t for t in trades if t.get("exit_type") != "OPEN"]
    total, win_rate, expectancy = recompute_trade_stats(closed)
    summary = {
        "symbol":     symbol,
        "atr_mean":   atr_mean,
        "sharpe":     sharpe,
        "drawdown":   ddown_pct,
        "trades":     total,
        "win_rate":   win_rate,
        "expectancy": expectancy,
    }
    for k in (
        "fast","mid1","mid2","mid3",
        "adx_period","adx_threshold",
        "atr_period","atr_mult",
        "sl_mode","sl_value",
        "use_sl_tg","use_trailing","trail_atr_mult",
        "use_signal_exit","reentry_cooldown","ignore_before",
        "tg_mode","tg1","tg2","tg3",    # profit-target fields
    ):
        if k in base_params:
            summary[k] = base_params[k]

    return summary, trades

# MAIN entry
def main():
    print(f"Starting morningscan backtest on {RUN_DATE}")
    run_str = RUN_DATE.strftime("%Y%m%d")
    scan_csv    = os.path.join(RESULTS_DIR, f"morning_scanner_{run_str}.csv")
    summary_out = os.path.join(RESULTS_DIR, f"scanbt_summary_{run_str}.csv")
    trades_out  = os.path.join(RESULTS_DIR, f"scanbt_trades_{run_str}.csv")

    scan_df = pd.read_csv(scan_csv).head(10)
    if scan_df.empty:
        print(f"[WARN] scanner file {scan_csv} is empty. Exiting.")
        return

    token_map    = dict(fetch_symbols(active=None, type_filter="EQ"))
    burn_in      = (RUN_DATE - timedelta(days=15)).strftime("%Y-%m-%d 00:00:00")
    period_start = RUN_DATE.strftime("%Y-%m-%d 09:30:00")
    period_end   = RUN_DATE.strftime("%Y-%m-%d 15:30:00")

    summaries, all_trades = [], []
    for sym in scan_df["symbol"]:
        tok = token_map.get(sym)
        if not tok:
            print(f"[WARN] no token for {sym}; skipping")
            continue
        print(f"\n=== Backtesting {sym} from {period_start} to {period_end} ===")
        try:
            summary, trades = run_backtest_for(
                sym, tok, burn_in, period_start, period_end, PARAMS
            )
        except Exception as e:
            print(f"[ERROR] {sym} backtest failed: {e}")
            continue
        if summary:
            print(
                f"Loaded data: {summary['trades']} trades, "
                f"win_rate={summary['win_rate']:.1f}%, "
                f"expectancy={summary['expectancy']:.3f}"
            )
            summaries.append(summary)
            all_trades.extend(trades)
        else:
            print(f"[INFO] No trades for {sym}")

    pd.DataFrame(summaries).to_csv(summary_out, index=False)
    print(f"Wrote summary  {summary_out}")
    pd.DataFrame(all_trades).to_csv(trades_out,   index=False)
    print(f"Wrote trades   {trades_out}")

if __name__ == "__main__":
    main()
