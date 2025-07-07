#!/usr/bin/env python3
import os
import sys

# ─── ensure project root is on PYTHONPATH ───────────────────────────────────────
# so that `import config` and `import models` work even when running this file directly
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ─── imports ────────────────────────────────────────────────────────────────────
import pandas as pd
from sqlalchemy import text

from config.db import get_session


def load_candles(symbol: str,
                 start:   str,
                 end:     str) -> pd.DataFrame:
    """
    Load 1-minute candles for `symbol` between `start` and `end` (ISO strings)
    from the backtest candles table.
    Returns a DataFrame with a DatetimeIndex and columns ['open','high','low','close','volume'].
    """
    query = text("""
        SELECT candle_time    AS dt,
               `open`, `high`, `low`, `close`, `volume`
          FROM candles
         WHERE symbol    = :symbol
           AND frequency = 1
           AND candle_time BETWEEN :start AND :end
         ORDER BY candle_time
    """)

    with get_session() as session:
        df = pd.read_sql(query, session.bind, params={
            "symbol": symbol,
            "start":  start,
            "end":    end
        })

    # Convert to actual DatetimeIndex (with tz if needed)
    df["dt"] = pd.to_datetime(df["dt"])
    df.set_index("dt", inplace=True)
    return df


if __name__ == "__main__":
    # Quick smoke test when running python data/load_candles.py
    df = load_candles("INFY", "2025-04-01", "2025-07-06")
    print("Loaded rows:", len(df))
    print(df.head(), "\n…\n", df.tail())
