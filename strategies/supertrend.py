import backtrader as bt

class SuperTrend(bt.Indicator):
    lines = ("st",)
    params = dict(period=120, multiplier=3.0)

    def __init__(self):
        self.atr = bt.ind.ATR(self.data, period=self.p.period)
        self.hl2 = (self.data.high + self.data.low) / 2
        # we need one extra bar so ATR[0] is valid exactly at len == period+1
        self.addminperiod(self.p.period + 1)

    def next(self):
        l   = len(self)
        price = self.data.close[0]
        hl2   = self.hl2[0]
        atr   = self.atr[0]

        # 1) For the VERY first period bars, just fill with hl2
        if l <= self.p.period:
            self.lines.st[0] = hl2
            return

        # 2) On the first bar where ATR is valid (l == period+1),
        #    initialize to hl2 ± ATR×mult depending on price
        upper = hl2 + self.p.multiplier * atr
        lower = hl2 - self.p.multiplier * atr
        if l == self.p.period + 1:
            self.lines.st[0] = upper if price > upper else lower
            return

        # 3) Thereafter, follow the standard band logic
        prev = self.lines.st[-1]
        if price > prev:
            self.lines.st[0] = min(upper, prev)
        else:
            self.lines.st[0] = max(lower, prev)


class ST(bt.Strategy):
    params = dict(
        st_period=120,
        st_mult=3.0,
        eval_start=None  # datetime to start trading
    )

    def __init__(self):
        # attach corrected indicator
        self.st = SuperTrend(
            self.data,
            period=self.p.st_period,
            multiplier=self.p.st_mult
        )
        self.prev_up = None

    def next(self):
        dt = self.data.datetime.datetime(0)
        # skip until eval_start
        if self.p.eval_start and dt < self.p.eval_start:
            return

        price  = float(self.data.close[0])
        st_val = float(self.st[0])
        curr_up = price > st_val

        # initialize
        if self.prev_up is None:
            self.prev_up = curr_up
            return

        # on flip up
        if curr_up and not self.prev_up:
            print(f"{dt}  ⬆ BUY  price={price:.2f}  st={st_val:.2f}")
            self.buy()

        # on flip down
        elif not curr_up and self.prev_up:
            print(f"{dt}  ⬇ SELL price={price:.2f}  st={st_val:.2f}")
            self.close()

        self.prev_up = curr_up
