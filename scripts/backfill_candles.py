#!/usr/bin/env python3
"""
Backfill INFY 1-minute candles into the backtest DB using KiteConnect.
Fields and filters have been updated to match your Candle model.
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
ACCESS_TOKEN = "6w2AQw8fj5Ks5bXUcIlJ9aR1ymtSaAtN"

SYMBOL = "INFY"
TOKEN  = 408065   # NSE instrument_token for INFY

START_DATE = "2025-05-31"
END_DATE   = "2025-06-30"

# Only backfilling 1-minute for now
FREQUENCIES = ["1m"]

# Map shorthand to Kite interval *and* to integer minute
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

def backfill_symbol(
    kite:    KiteConnect,
    session,
    symbol:  str,
    token:   int,
    freq:    str,
    start:   datetime,
    end:     datetime
) -> None:
    """Fetch and upsert historical bars for one symbol/timeframe."""
    interval, freq_num = INTERVAL_MAP[freq]

    print(f"Fetching {symbol} @ {freq} ({interval}) from {start} to {end}")
    bars = kite.historical_data(
        instrument_token=token,
        from_date=start,
        to_date=end,
        interval=interval
    )

    # Delete any overlapping rows in backtest.candles
    session.query(Candle).filter(
        Candle.symbol      == symbol,
        Candle.frequency   == freq_num,
        Candle.candle_time.between(start, end)
    ).delete(synchronize_session=False)
    session.commit()

    # Insert fresh bars
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
    # Parse & expand date range
    start_dt = datetime.fromisoformat(START_DATE)
    end_dt   = datetime.fromisoformat(END_DATE) + timedelta(hours=23, minutes=59)

    # Init Kite client
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)

    with get_session() as session:
        print(f"Backfilling {SYMBOL} (token={TOKEN})")
        for freq in FREQUENCIES:
            backfill_symbol(kite, session, SYMBOL, TOKEN, freq, start_dt, end_dt)

    print("✅ Backfill complete.")


if __name__ == "__main__":
    main()
