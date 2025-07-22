import backtrader as bt

class SuperTrend(bt.Indicator):
    lines = ("st", "final_up", "final_dn", "trend")
    params = dict(period=20, multiplier=3.0)

    def __init__(self):
        self.atr = bt.indicators.ATR(self.data, period=self.p.period)
        hl2 = (self.data.high + self.data.low) / 2.0
        self.basic_up = hl2 + self.p.multiplier * self.atr
        self.basic_dn = hl2 - self.p.multiplier * self.atr
        self.addminperiod(self.p.period + 1)

    def next(self):
        if len(self) == self.p.period + 1:
            self.final_up[0] = self.basic_up[0]
            self.final_dn[0] = self.basic_dn[0]
            self.trend[0]    = 1
            self.st[0]       = self.basic_dn[0]
            return

        prev_fu = self.final_up[-1]
        prev_fd = self.final_dn[-1]

        self.final_up[0] = self.basic_up[0] if (self.basic_up[0] < prev_fu or self.data.close[-1] > prev_fu) else prev_fu
        self.final_dn[0] = self.basic_dn[0] if (self.basic_dn[0] > prev_fd or self.data.close[-1] < prev_fd) else prev_fd

        if self.data.close[0] > self.final_up[-1]:
            self.trend[0] = 1
        elif self.data.close[0] < self.final_dn[-1]:
            self.trend[0] = -1
        else:
            self.trend[0] = self.trend[-1]

        self.st[0] = self.final_dn[0] if self.trend[0] > 0 else self.final_up[0]


class ST(bt.Strategy):
    params = dict(st_period=20, st_mult=3.0, eval_start=None)

    def __init__(self):
        self.st    = SuperTrend(self.data, period=self.p.st_period, multiplier=self.p.st_mult)
        self.atr14 = bt.indicators.ATR(self.data, period=14)

        self.prev_up = None
        self.last_atr_on_entry   = None
        self.last_close_on_entry = None

    def next(self):
        dt = self.data.datetime.datetime(0)
        if self.p.eval_start and dt < self.p.eval_start:
            return

        price  = float(self.data.close[0])
        st_val = float(self.st.st[0])
        up_now = price > st_val

        if self.prev_up is None:
            self.prev_up = up_now
            return

        if up_now and not self.prev_up:
            self.last_atr_on_entry   = float(self.atr14[0])
            self.last_close_on_entry = price
            self.buy()
        elif not up_now and self.prev_up:
            self.close()

        self.prev_up = up_now

    def notify_order(self, order):
        if order.status != order.Completed:
            return
        # nothing else needed
