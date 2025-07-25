import backtrader as bt

class AdaptiveSuperTrend(bt.Indicator):
    """
    Autotuning SuperTrend:
      base_mult = a_coef + b_coef  avg_atr
      dyn_mult  = base_mult  (avg_atr / atr)
    """
    lines = ("st",)
    params = dict(
        period       = 240,     # ATR lookback for ST
        vol_lookback = 240,     # smoothing window for baseline ATR
        a_coef       = -1.4218, # intercept from JanJun fit
        b_coef       =  3.9862, # slope from JanJun fit
        min_mult     = 0.5,     # clamp lower bound
        max_mult     = 3.0,     # clamp upper bound
    )

    def __init__(self):
        # 1) raw ATR
        atr = bt.indicators.ATR(self.data, period=self.p.period)

        # 2) baseline ATR for current regime
        avg_atr = bt.indicators.EMA(atr, period=self.p.vol_lookback)

        # 3) compute nominal multiplier from regression
        base_mult = self.p.a_coef + self.p.b_coef * avg_atr

        # 4) clamp it
        base_mult = bt.If(
            base_mult < self.p.min_mult,
            self.p.min_mult,
            bt.If(base_mult > self.p.max_mult,
                  self.p.max_mult,
                  base_mult)
        )

        # 5) scale so that dyn_mult * atr == base_mult * avg_atr
        dyn_mult = base_mult * (avg_atr / atr)

        # 6) compute SuperTrend bands
        hl2   = (self.data.high + self.data.low) / 2
        upper = hl2 + dyn_mult * atr
        lower = hl2 - dyn_mult * atr

        # 7) recursive SuperTrend line
        self.l.st = bt.If(
            self.data.close > self.l.st(-1),
            bt.Min(upper, self.l.st(-1)),
            bt.Max(lower, self.l.st(-1)),
        )

class STAdaptive(bt.Strategy):
    params = dict(
        st_period    = 240,
        vol_lookback = 240,
        a_coef       = -1.4218,
        b_coef       =  3.9862,
        min_mult     = 0.5,
        max_mult     = 3.0,
    )

    def __init__(self):
        self.st = AdaptiveSuperTrend(
            self.data,
            period       = self.p.st_period,
            vol_lookback = self.p.vol_lookback,
            a_coef       = self.p.a_coef,
            b_coef       = self.p.b_coef,
            min_mult     = self.p.min_mult,
            max_mult     = self.p.max_mult,
        )

    def next(self):
        price = self.data.close[0]
        if not self.position and price > self.st.st[0]:
            self.buy()
        elif self.position and price < self.st.st[0]:
            self.close()


class FixedWidthSuperTrend(bt.Indicator):
    """
    SuperTrend with a constant absolute channel width.
      target_width = vol_baseline_JanJun * best_mult_JanJun
      dyn_mult      = target_width / ATR
    """
    lines = ("st",)
    params = dict(
        period       = 240,    # ATR lookback
        target_width = 2.38,   # e.g. JanJun vol_baseline * best_mult
    )

    def __init__(self):
        # 1) ATR for this bar
        atr = bt.indicators.ATR(self.data, period=self.p.period)

        # 2) dynamic multiplier so that dyn_mult*atr == target_width
        dyn_mult = self.p.target_width / atr

        # 3) compute the usual ST bands
        hl2   = (self.data.high + self.data.low) / 2
        upper = hl2 + dyn_mult * atr
        lower = hl2 - dyn_mult * atr

        # 4) recursive ST line
        self.l.st = bt.If(
            self.data.close > self.l.st(-1),
            bt.Min(upper, self.l.st(-1)),
            bt.Max(lower, self.l.st(-1)),
        )


class STFixedWidth(bt.Strategy):
    """
    Strategy wrapper for FixedWidthSuperTrend.
    """
    params = dict(
        st_period    = 240,
        target_width = 3.3641,
    )

    def __init__(self):
        self.st = FixedWidthSuperTrend(
            self.data,
            period       = self.p.st_period,
            target_width = self.p.target_width,
        )

    def next(self):
        price = self.data.close[0]
        if not self.position and price > self.st.st[0]:
            self.buy()
        elif self.position and price < self.st.st[0]:
            self.close()
