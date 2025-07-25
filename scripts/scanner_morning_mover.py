#!/usr/bin/env python3
# scripts/scanner_morning_mover.py

import os
import sys
import logging
import pandas as pd
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from kiteconnect import KiteConnect

#  Project root 
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

#  Results folder 
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

#  Kite credentials 
API_KEY      = "bv185n0541aaoish"
ACCESS_TOKEN = "1andO40s4rkUL7dANHRp06UPuv6wvUvY"

#  Scanner config 
RUN_DATE       = "2025-07-25"    #  the date you want to scan
TIMEZONE       = "Asia/Kolkata"
LOOKBACK_DAYS  = 7               # warmup window
FREQUENCY_KEY  = "15min"         # intraday bar size
OPEN_TIME      = time(9, 30)     # which bar on RUN_DATE to measure

#  Map your frequencies to Kites API 
VALID_FREQS = {
    "1min":  "minute",
    "3min":  "3minute",
    "5min":  "5minute",
    "10min": "10minute",
    "15min": "15minute",
    "30min": "30minute",
    "60min": "60minute",
    "day":   "day",
}

#  Pull your symbol/token list 
from data.get_symbols import fetch_symbols  # returns List[Tuple[symbol:str, token:int]]

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")


def fetch_intraday(symbol: str, token: int,
                   start_dt: datetime, end_dt: datetime,
                   freq_key: str) -> pd.DataFrame:
    """Get Kite intraday bars between two timezoneaware datetimes."""
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)
    interval = VALID_FREQS[freq_key]

    bars = kite.historical_data(
        instrument_token=token,
        from_date=start_dt,
        to_date=end_dt,
        interval=interval
    )
    df = pd.DataFrame(bars)

    def _ensure_tz(x):
        # Kite sometimes gives pure datestrings ("YYYY-MM-DD") for old bars
        if isinstance(x, str) and len(x) == 10:
            d0 = datetime.strptime(x, "%Y-%m-%d")
            return d0.replace(tzinfo=ZoneInfo(TIMEZONE))
        dt0 = pd.to_datetime(x).to_pydatetime()
        if dt0.tzinfo is None:
            dt0 = dt0.replace(tzinfo=ZoneInfo(TIMEZONE))
        return dt0

    df["date"] = df["date"].apply(_ensure_tz)
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)

    return df[["open", "high", "low", "close", "volume"]]


def compute_movers(symbols, run_date: date):
    # build datetime bounds
    start_date = run_date - timedelta(days=LOOKBACK_DAYS)
    dt_start = datetime.combine(start_date, time(0, 0), tzinfo=ZoneInfo(TIMEZONE))
    dt_end   = datetime.combine(run_date, OPEN_TIME, tzinfo=ZoneInfo(TIMEZONE))

    # figure out how far back the bar starts
    mins = int(''.join(filter(str.isdigit, FREQUENCY_KEY)))  # e.g. "15min"  15
    dt_bar = dt_end - timedelta(minutes=mins)                # e.g. 09:3015min = 09:15 stamp

    movers = []
    for symbol, token in symbols:
        try:
            df = fetch_intraday(symbol, token, dt_start, dt_end, FREQUENCY_KEY)
        except Exception as e:
            log.warning(f"{symbol:<10} fetch failed: {e}")
            continue

        # require enough history
        hist = df[df.index < dt_bar]
        if len(hist) < LOOKBACK_DAYS:
            log.info(f"{symbol:<10} insufficient bars ({len(hist)})")
            continue

        # look strictly for the "09:15" bar (start of the 09:1509:30 interval)
        today = df[df.index == dt_bar]
        if today.empty:
            log.info(f"{symbol:<10} missing openbar at {dt_bar.isoformat()}")
            continue

        o = float(today.open.iloc[0])
        c = float(today.close.iloc[0])
        movers.append({
            "symbol": symbol,
            "open":   o,
            "close":  c,
            "move":   c - o
        })

    return movers


def main():
    run_date = datetime.strptime(RUN_DATE, "%Y-%m-%d").date()

    try:
        symbols = fetch_symbols(active=None, type_filter="EQ")
    except Exception as e:
        log.error("Could not fetch symbols: %s", e)
        return

    log.info(f"Scanning {len(symbols)} symbols for {run_date} (lookback {LOOKBACK_DAYS}d)")

    movers = compute_movers(symbols, run_date)
    df = pd.DataFrame(movers)
    # rank by magnitude, not signed value
    df["abs_move"] = df["move"].abs()
    df = df.sort_values("abs_move", ascending=False).drop(columns="abs_move")

    out_path = os.path.join(RESULTS_DIR, f"scanner_{run_date:%Y%m%d}_movers.csv")
    df.to_csv(out_path, index=False)

    log.info(f"Wrote {out_path}")
    log.info("Top 10 movers:\n%s", df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
