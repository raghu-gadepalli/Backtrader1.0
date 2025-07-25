#!/usr/bin/env python3
import os
import sys

#  ensure project root is on PYTHONPATH 
# so that `import config` and `import models` work even when running this file directly
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

#  imports 
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


def load_candles_with_history(symbol: str,
                              start:   str,
                              end:     str,
                              history_bars: int) -> pd.DataFrame:
    """
    Fetch last `history_bars` 1min candles before `start` plus
    all candles between `start` and `end`. Returns a single DataFrame.
    """
    # 1) history portion
    hist_q = text("""
        SELECT candle_time AS dt, `open`,`high`,`low`,`close`,`volume`
          FROM candles
         WHERE symbol    = :symbol
           AND frequency = 1
           AND candle_time < :start
         ORDER BY candle_time DESC
         LIMIT :hb
    """)
    with get_session() as sess:
        df_hist = pd.read_sql(hist_q, sess.bind,
                              params={"symbol":symbol,
                                      "start": start,
                                      "hb":    history_bars})
    df_hist["dt"] = pd.to_datetime(df_hist["dt"])
    df_hist.set_index("dt", inplace=True)
    df_hist.sort_index(inplace=True)

    # 2) main window portion
    df_main = load_candles(symbol, start, end)

    # 3) concat & return
    return pd.concat([df_hist, df_main])



if __name__ == "__main__":
    # Quick smoke test when running python data/load_candles.py
    df = load_candles("INFY", "2025-04-01", "2025-07-06")
    print("Loaded rows:", len(df))
    print(df.head(), "\n\n", df.tail())
