#!/usr/bin/env python3
"""
Backfill multiple symbols into the backtest DB using KiteConnect.
"""

import os
import sys
from datetime import datetime, timedelta
from kiteconnect import KiteConnect

# ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db           import get_session
from models.trade_models import Candle

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────

API_KEY      = "bv185n0541aaoish"
ACCESS_TOKEN = "CfDISGqbsQG7qCtBoY5ifoJY55l1cBg7"

# Define list of (SYMBOL, TOKEN)

SYMBOLS = [
    ("AXISBANK",   1510401),
    ("HDFCBANK",   341249),
    ("ICICIBANK",  1270529),
    ("INFY",       408065),
    ("KOTAKBANK",  492033),
    ("MARUTI",     2815745),
    ("NIFTY 50",   256265),
    ("NIFTY BANK", 260105),
    ("RELIANCE",   738561),
    ("SBIN",       779521),
    ("SUNPHARMA",  857857),
    ("TATAMOTORS", 884737),
    ("TCS",        2953217),
    ("TECHM",      3465729),
]




# START_DATE = "2025-06-01"
# END_DATE   = "2025-07-07"

START_DATE = "2025-01-01"
END_DATE   = "2025-02-28"

FREQUENCIES = ["1m"]

INTERVAL_MAP = {
    "1m":  ("minute",  1),
    "3m":  ("3minute", 3),
    "5m":  ("5minute", 5),
    "15m": ("15minute",15),
    "30m": ("30minute",30),
    "60m": ("60minute",60),
    "1d":  ("day",     1440),
}


# ─── BACKFILL LOGIC ────────────────────────────────────────────────────────────

def backfill_symbol(kite, session, symbol, token, freq, start, end):
    interval, freq_num = INTERVAL_MAP[freq]

    print(f"Fetching {symbol} @ {freq} ({interval}) from {start} to {end}")
    bars = kite.historical_data(
        instrument_token=token,
        from_date=start,
        to_date=end,
        interval=interval
    )

    session.query(Candle).filter(
        Candle.symbol      == symbol,
        Candle.frequency   == freq_num,
        Candle.candle_time.between(start, end)
    ).delete(synchronize_session=False)
    session.commit()

    for b in bars:
        session.add(Candle(
            symbol      = symbol,
            frequency   = freq_num,
            candle_time = b["date"],
            open        = b["open"],
            high        = b["high"],
            low         = b["low"],
            close       = b["close"],
            volume      = b["volume"],
            oi          = b.get("oi", 0),
            active      = True
        ))
    session.commit()
    print(f"Inserted {len(bars)} rows for {symbol} @ {freq}")


def main():
    start_dt = datetime.fromisoformat(START_DATE)
    end_dt   = datetime.fromisoformat(END_DATE) + timedelta(hours=23, minutes=59)

    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)

    with get_session() as session:
        for symbol, token in SYMBOLS:
            print(f"\n📊 Backfilling {symbol} (token={token})")
            for freq in FREQUENCIES:
                backfill_symbol(kite, session, symbol, token, freq, start_dt, end_dt)

    print("\n✅ Backfill complete.")


if __name__ == "__main__":
    main()
