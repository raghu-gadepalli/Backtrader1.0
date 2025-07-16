import backtrader as bt

class AdaptiveSuperTrend(bt.Indicator):
    """
    SuperTrend whose multiplier adapts to recent volatility:
      dyn_mult = base_mult * (avg_atr / atr)
    so the channel widens in low‑vol and tightens in high‑vol regimes.
    """
    lines = ("st",)
    params = dict(
        period       = 120,    # ATR lookback for the ST calculation
        base_mult    = 3.0,    # “nominal” multiplier
        vol_lookback = 240,    # window to compute avg ATR
    )

    def __init__(self):
        # 1) raw ATR for threshold
        atr = bt.indicators.ATR(self.data, period=self.p.period)

        # 2) baseline ATR over a longer window
        avg_atr = bt.indicators.SimpleMovingAverage(atr,
                                                    period=self.p.vol_lookback)

        # 3) dynamic multiplier
        dyn_mult = self.p.base_mult * (avg_atr / atr)

        # 4) compute upper/lower bands
        hl2   = (self.data.high + self.data.low) / 2
        upper = hl2 + dyn_mult * atr
        lower = hl2 - dyn_mult * atr

        # 5) recursive ST line
        self.l.st = bt.If(
            self.data.close > self.l.st(-1),
            bt.Min(upper, self.l.st(-1)),
            bt.Max(lower, self.l.st(-1)),
        )


class STAdaptive(bt.Strategy):
    """
    SuperTrend strategy that uses the AdaptiveSuperTrend indicator.
    """
    params = dict(
        st_period    = 240,   # ATR lookback for ST
        base_mult    = 1.8,   # nominal multiplier (anchored to Jan ATR)
        vol_lookback = 240,   # ATR window for volatility baseline
    )

    def __init__(self):
        self.st = AdaptiveSuperTrend(
            self.data,
            period       = self.p.st_period,
            base_mult    = self.p.base_mult,
            vol_lookback = self.p.vol_lookback,
        )

    def next(self):
        price = self.data.close[0]
        if not self.position and price > self.st.st[0]:
            self.buy()
        elif self.position and price < self.st.st[0]:
            self.close()
