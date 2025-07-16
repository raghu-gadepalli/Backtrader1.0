import backtrader as bt

#  SuperTrend indicator 
class SuperTrend(bt.Indicator):
    lines = ("st",)
    params = dict(period=120, multiplier=3.0)

    def __init__(self):
        atr   = bt.ind.ATR(self.data, period=self.p.period)
        hl2   = (self.data.high + self.data.low) / 2
        upper = hl2 + self.p.multiplier * atr
        lower = hl2 - self.p.multiplier * atr

        # recursive ST line
        self.l.st = bt.If(
            self.data.close > self.l.st(-1),
            bt.Min(upper, self.l.st(-1)),
            bt.Max(lower, self.l.st(-1)),
        )


#  SuperTrendonly strategy 
class ST(bt.Strategy):              #  strategy is now simply ST
    params = dict(st_period=120, st_mult=3.0)

    def __init__(self):
        # instantiate the indicator by its new name
        self.st = SuperTrend(self.data,
                             period=self.p.st_period,
                             multiplier=self.p.st_mult)

    def next(self):
        price = self.data.close[0]
        if not self.position and price > self.st[0]:
            self.buy()
        elif self.position and price < self.st[0]:
            self.close()
