import backtrader as bt

class MacdStrategy(bt.Strategy):
    params = dict(
        macd1      = 120,
        macd2      = 240,
        signal     = 60,
        hist_thresh= 0.00075,
        printlog   = False,   # now a proper param
    )

    def __init__(self, *args, **kwargs):
        # call the base __init__ so bt can wire everything up
        super().__init__(*args, **kwargs)

        # now you can read self.p.printlog if you want to gate debug prints
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1   = self.p.macd1,
            period_me2   = self.p.macd2,
            period_signal= self.p.signal
        )
        self.xover = bt.indicators.CrossOver(self.macd.macd,
                                             self.macd.signal)

    def next(self):
        hist = self.macd.macd[0] - self.macd.signal[0]
        if not self.position:
            if self.xover > 0 and hist > self.p.hist_thresh:
                if self.p.printlog:
                    dt = self.data.datetime.datetime(0)
                    print(f"{dt.isoformat()} BUY (hist={hist:.5f})")
                self.buy()
        else:
            if self.xover < 0 and hist < -self.p.hist_thresh:
                if self.p.printlog:
                    dt = self.data.datetime.datetime(0)
                    print(f"{dt.isoformat()} SELL (hist={hist:.5f})")
                self.sell()
