import backtrader as bt

class RenkoEMAStrategy(bt.Strategy):
    params = dict(
        fast_period=20,
        slow_period=50,
        renko_brick_size=0.5,  # Adjust this based on volatility
        printlog=True
    )

    def __init__(self):
        # Apply Renko filter
        self.data.addfilter(bt.filters.Renko, size=self.p.renko_brick_size)

        # Exponential Moving Averages on Renko bricks
        self.fast_ema = bt.ind.EMA(self.data, period=self.p.fast_period)
        self.slow_ema = bt.ind.EMA(self.data, period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.fast_ema, self.slow_ema)

    def log(self, txt, dt=None):
        if not self.p.printlog:
            return
        dt = dt or self.data.datetime.datetime(0)
        print(f'{dt.isoformat()} {txt}')

    def next(self):
        if not self.position:
            if self.crossover[0] > 0:
                self.log(f'BUY @ {self.data.close[0]:.2f}')
                self.buy()
        elif self.crossover[0] < 0:
            self.log(f'SELL @ {self.data.close[0]:.2f}')
            self.close()

    def stop(self):
        pnl = self.broker.getvalue() - self.broker.startingcash
        self.log(f'Final PnL: {pnl:.2f}')
