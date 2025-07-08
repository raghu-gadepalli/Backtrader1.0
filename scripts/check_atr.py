from data.load_candles import load_candles
import pandas as pd

symbols = ['INFY', 'RELIANCE', 'ICICIBANK']
atr_results = []

for sym in symbols:
    # Load minute bars
    df = load_candles(sym, '2025-04-01', '2025-07-06')
    
    # True Range (TR)
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    
    # ATR(14)
    atr14 = tr.rolling(14).mean()
    atr_last = atr14.iloc[-1]
    
    atr_results.append({
        'symbol': sym,
        'atr14_last': round(atr_last, 4)
    })

print(pd.DataFrame(atr_results))
