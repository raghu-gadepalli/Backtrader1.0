# strategies/HmaTrendStrategy.py

import backtrader as bt

class HmaTrendStrategy(bt.Strategy):
    params = (
        ("fast", 2000),   # fast HMA period
        ("slow",  600),   # slow HMA period
        ("printlog", False),
    )

    def __init__(self):
        price = self.data.close

        # Hull Moving Averages
        self.hma_fast = bt.indicators.HullMovingAverage(
            price, period=self.p.fast, plotname=f"HMA_FAST({self.p.fast})"
        )
        self.hma_slow = bt.indicators.HullMovingAverage(
            price, period=self.p.slow, plotname=f"HMA_SLOW({self.p.slow})"
        )

    def log(self, txt, dt=None):
        """ Logging helper """
        if self.p.printlog:
            dt = dt or self.data.datetime[0]
            dt = bt.num2date(dt)
            print(f"{dt.isoformat()} — {txt}")

    def next(self):
        # Check current position size: 0 = flat, >0 = long, <0 = short
        pos_size = self.position.size

        # Detect a crossover: HMA fast crossing above/below slow
        prev_fast = self.hma_fast[-1]
        prev_slow = self.hma_slow[-1]
        curr_fast = self.hma_fast[0]
        curr_slow = self.hma_slow[0]

        # Entry logic
        if pos_size == 0:
            # Bullish flip: fast crosses from <= slow to > slow
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                self.log("BUY signal (HMA flip)", self.data.datetime[0])
                self.buy()
            # Bearish flip: fast crosses from >= slow to < slow
            elif prev_fast >= prev_slow and curr_fast < curr_slow:
                self.log("SELL signal (HMA flip)", self.data.datetime[0])
                # Enter short
                self.sell()

        # Exit logic
        elif pos_size > 0:
            # Exit long on bearish flip
            if curr_fast < curr_slow:
                self.log("EXIT LONG (HMA flip)", self.data.datetime[0])
                self.close()

        elif pos_size < 0:
            # Exit short on bullish flip
            if curr_fast > curr_slow:
                self.log("EXIT SHORT (HMA flip)", self.data.datetime[0])
                self.close()

    def stop(self):
        # Optionally print final P/L
        pnl = round(self.broker.getvalue() - self.broker.startingcash, 2)
        self.log(f"Ending PnL: {pnl}", dt=self.data.datetime[0])
