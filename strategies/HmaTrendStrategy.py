# strategies/HmaTrendStrategy.py

import backtrader as bt

class HmaTrendStrategy(bt.Strategy):
    params = (
        ("fast", 2000),   # default fast HMA period
        ("slow",  600),   # default slow HMA period
    )

    def __init__(self):
        # reference to the close price line
        price = self.data.close

        # fast & slow Hull Moving Averages
        self.hma_fast = bt.indicators.HullMovingAverage(price,
                                period=self.p.fast, plotname=f"HMA_FAST({self.p.fast})")
        self.hma_slow = bt.indicators.HullMovingAverage(price,
                                period=self.p.slow, plotname=f"HMA_SLOW({self.p.slow})")

    def next(self):
        # no trading logic yet—we're just plotting
        pass
