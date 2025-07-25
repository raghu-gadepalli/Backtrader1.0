#!/usr/bin/env python3
# scripts/scanner_morning_mover.py

import os
import sys
import csv
import logging
from datetime import datetime, date, time as dtime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from pandas.tseries.offsets import BDay

# allow imports from project root
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Results directory
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

from data.get_symbols import fetch_symbols  # returns List[Tuple[symbol:str, token:int]]
from data.load_candles_kite import load_candles_kite  # returns DataFrame with OHLCV

# Settings
RUN_DATE          = "2025-07-23"  # format: YYYY-MM-DD
TIMEZONE          = "Asia/Kolkata"
OPEN_TIME         = dtime(9, 15)
LOOKBACK_DAYS     = 20
FREQUENCY         = "15minute"
MIN_OPENING_BARS  = 15

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def compute_stats_and_today(symbols, run_date):
    tz = ZoneInfo(TIMEZONE)
    # business-day lookback
    start_date = (pd.Timestamp(run_date) - BDay(LOOKBACK_DAYS)).date()
    start_dt   = datetime.combine(start_date, OPEN_TIME, tzinfo=tz)
    end_dt     = datetime.combine(run_date, OPEN_TIME, tzinfo=tz)

    logger.info(f"Fetching data from {start_date} to {run_date} for {len(symbols)} symbols")
    hist_stats, today_bars, audit = {}, {}, []

    for symbol, token in symbols:
        rec = {"symbol": symbol}
        try:
            df = load_candles_kite(symbol, token, start_dt, end_dt, frequency=FREQUENCY)
        except Exception as e:
            logger.warning(f"{symbol:<8} fetch error: {e}")
            rec.update({"status": "error", "reason": str(e)})
            audit.append(rec)
            continue

        rec["total_bars"] = len(df)
        if df.empty:
            rec.update({"status": "skipped", "reason": "no data"})
            audit.append(rec)
            continue

        opening = df[df.index.time == OPEN_TIME]
        rec["opening_bars"] = len(opening)
        if len(opening) < MIN_OPENING_BARS:
            rec.update({"status": "skipped", "reason": f"only {len(opening)} opening bars (<{MIN_OPENING_BARS})"})
            audit.append(rec)
            continue

        history = opening.iloc[:-1]
        today   = opening.iloc[-1]
        rec.update({"history_bars": len(history), "today_time": today.name})

        avg_r = float((history["high"] - history["low"]).mean())
        avg_v = float(history["volume"].mean())
        rec.update({"avg_range": avg_r, "avg_volume": avg_v, "status": "included"})

        hist_stats[symbol] = {"avg_range": avg_r, "avg_volume": avg_v}
        today_bars[symbol] = today
        audit.append(rec)

        logger.info(f"{symbol:<8} hist={len(history):>2} avg_r={avg_r:.2f} avg_v={avg_v:.0f} today={today.name}")

    return hist_stats, today_bars, audit


def main():
    try:
        run_date = datetime.strptime(RUN_DATE, "%Y-%m-%d").date()
    except ValueError:
        logger.error("RUN_DATE must be YYYY-MM-DD")
        return

    date_str   = run_date.strftime("%Y%m%d")
    csv_file   = os.path.join(RESULTS_DIR, f"morning_scanner_{date_str}.csv")
    audit_file = os.path.join(RESULTS_DIR, f"morning_scan_audit_{date_str}.csv")

    symbols = fetch_symbols(active=None, type_filter="EQ") or []
    logger.info(f"Loaded {len(symbols)} symbols for {run_date}")

    stats, today_bars, audit = compute_stats_and_today(symbols, run_date)
    included = len(stats)
    logger.info(f"{included}/{len(symbols)} symbols passed inclusion criteria")

    # scoring
    results = []
    for symbol, _ in symbols:
        if symbol in stats and symbol in today_bars:
            avg_r = stats[symbol]["avg_range"]
            avg_v = stats[symbol]["avg_volume"]
            bar   = today_bars[symbol]
            rng   = float(bar["high"] - bar["low"])
            vol   = int(bar["volume"])
            rd    = (rng - avg_r) / avg_r if avg_r else 0
            vd    = (vol - avg_v) / avg_v if avg_v else 0
            score = 0.7 * rd + 0.3 * vd
            direction = "BUY" if bar["close"] > bar["open"] else "SELL"
            results.append({
                "symbol":       symbol,
                "avg_range":    round(avg_r, 2),
                "avg_volume":   round(avg_v),
                "today_range":  round(rng, 2),
                "today_volume": vol,
                "range_dev":    round(rd, 4),
                "vol_dev":      round(vd, 4),
                "score":        round(score, 4),
                "direction":    direction,
            })

    # write audit
    pd.DataFrame(audit).to_csv(audit_file, index=False)
    logger.info(f"Audit saved to {audit_file}")

    # sort & dedupe
    sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)
    unique = []
    seen = set()
    for r in sorted_results:
        if r["symbol"] not in seen:
            unique.append(r)
            seen.add(r["symbol"])

    # write full results
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=unique[0].keys())
        writer.writeheader()
        writer.writerows(unique)
    logger.info(f"Results saved to {csv_file}")

    # log top 10
    logger.info("Top 10 movers:")
    for r in unique[:10]:
        logger.info(f"{r['symbol']:<8} {r['direction']:>4} score={r['score']} rng={r['today_range']} vol={r['today_volume']}")


if __name__ == "__main__":
    main()
