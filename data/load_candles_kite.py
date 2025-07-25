# data/load_candles_kite.py

import pandas as pd
from datetime import datetime
from kiteconnect import KiteConnect

#  Your Kite credentials 
API_KEY      = "bv185n0541aaoish"
ACCESS_TOKEN = "1andO40s4rkUL7dANHRp06UPuv6wvUvY"

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

def load_candles_kite(symbol: str,
                      token: int,
                      start:  str,
                      end:    str,
                      frequency: str = "1min") -> pd.DataFrame:
    """
    Fetch intraday / daily candles from Kite.
      symbol     : instrument symbol (for error messages)
      token      : instrument_token (int) passed to Kite
      start      : "YYYY-MM-DD HH:MM:SS" or ISO8601 string
      end        : same format as start
      frequency  : one of VALID_FREQS keys
    """
    # 1) Init Kite client
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)

    # 2) Normalize interval
    interval = VALID_FREQS.get(frequency, frequency)

    # 3) Fetch raw data
    try:
        bars = kite.historical_data(
            instrument_token=int(token),
            from_date=start,
            to_date=end,
            interval=interval
        )
    except Exception as e:
        raise RuntimeError(f"load_candles_kite() failed for {symbol}: {e}")

    # 4) Build DataFrame
    df = pd.DataFrame(bars)

    # 5) Normalize the `date` column (Kite returns "YYYY-MM-DD" for old bars)
    def _parse_dt(x):
        if isinstance(x, str) and len(x) == 10:
            # date-only string
            return datetime.strptime(x, "%Y-%m-%d")
        # full timestamp, pandas will handle tz or naive intelligently
        return pd.to_datetime(x)

    df["date"] = df["date"].apply(_parse_dt)

    # 6) Set index, sort, and strip any timezone info
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)
    try:
        df.index = df.index.tz_localize(None)
    except (AttributeError, ValueError):
        pass

    # 7) Return only OHLCV
    return df[["open", "high", "low", "close", "volume"]]
