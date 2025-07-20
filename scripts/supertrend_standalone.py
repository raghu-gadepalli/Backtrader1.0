import pandas as pd
import numpy as np

def compute_supertrend(df, period=10, multiplier=3):
    df = df.copy()
    hl2 = (df['high'] + df['low']) / 2
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        )
    )
    df['atr'] = df['tr'].rolling(period, min_periods=period).mean()
    df['upperband'] = hl2 + multiplier * df['atr']
    df['lowerband'] = hl2 - multiplier * df['atr']
    df['final_upperband'] = np.nan
    df['final_lowerband'] = np.nan

    # Initialize in_uptrend as a bool column (no more float warnings!)
    df['in_uptrend'] = np.full(len(df), False, dtype=bool)

    for i in range(len(df)):
        if np.isnan(df['atr'].iloc[i]):
            continue
        if i == 0 or np.isnan(df['atr'].iloc[i - 1]):
            df.at[df.index[i], 'final_upperband'] = df['upperband'].iloc[i]
            df.at[df.index[i], 'final_lowerband'] = df['lowerband'].iloc[i]
            df.at[df.index[i], 'in_uptrend'] = True
        else:
            prev = i - 1
            curr_upper = df['upperband'].iloc[i]
            curr_lower = df['lowerband'].iloc[i]
            prev_final_upper = df['final_upperband'].iloc[prev]
            prev_final_lower = df['final_lowerband'].iloc[prev]
            prev_close = df['close'].iloc[prev]
            prev_uptrend = df['in_uptrend'].iloc[prev]

            if (curr_upper < prev_final_upper) or (prev_close > prev_final_upper):
                final_upper = curr_upper
            else:
                final_upper = prev_final_upper

            if (curr_lower > prev_final_lower) or (prev_close < prev_final_lower):
                final_lower = curr_lower
            else:
                final_lower = prev_final_lower

            if prev_uptrend:
                in_uptrend = df['close'].iloc[i] >= final_lower
            else:
                in_uptrend = df['close'].iloc[i] > final_upper

            df.at[df.index[i], 'final_upperband'] = final_upper
            df.at[df.index[i], 'final_lowerband'] = final_lower
            df.at[df.index[i], 'in_uptrend'] = in_uptrend

    df['supertrend'] = np.where(df['in_uptrend'], df['final_lowerband'], df['final_upperband'])
    df['signal'] = 'HOLD'
    for i in range(1, len(df)):
        if df['in_uptrend'].iloc[i] and not df['in_uptrend'].iloc[i-1]:
            df.at[df.index[i], 'signal'] = 'BUY'
        elif not df['in_uptrend'].iloc[i] and df['in_uptrend'].iloc[i-1]:
            df.at[df.index[i], 'signal'] = 'SELL'
    return df

if __name__ == "__main__":
    filename = "./axis_candles.csv"
    df = pd.read_csv(filename)
    df['candle_time'] = pd.to_datetime(df['candle_time'], errors='coerce')
    for col in ['high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['high', 'low', 'close'])
    st = compute_supertrend(df, period=10, multiplier=3)
    date_filter = "2025-07-17"
    mask = st['candle_time'].dt.strftime("%Y-%m-%d") == date_filter
    today = st[mask].copy()
    print(f"Filtered to {len(today)} rows for {date_filter}\n")
    cols = ['candle_time', 'close', 'supertrend', 'in_uptrend', 'signal']
    flips = today[today['signal'].isin(['BUY', 'SELL'])][cols]
    print(f"\nFlips (BUY/SELL) for {date_filter}")
    print(flips)
    print("\nSignal counts:\n", today['signal'].value_counts().to_string())
