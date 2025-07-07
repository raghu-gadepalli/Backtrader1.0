import backtrader as bt

class HmaTrendStrategy(bt.Strategy):
    params = (
        ("fast",     600),    # fast < slow
        ("slow",    2000),
        ("printlog", False),
    )

    def __init__(self):
        price = self.data.close
        self.hma_fast = bt.indicators.HullMovingAverage(
            price, period=self.p.fast, plotname=f"HMA_FAST({self.p.fast})"
        )
        self.hma_slow = bt.indicators.HullMovingAverage(
            price, period=self.p.slow, plotname=f"HMA_SLOW({self.p.slow})"
        )
        self.order = None  # keep track of pending orders

    def log(self, txt, dt=None):
        if not self.p.printlog:
            return
        dt = dt or self.data.datetime[0]
        dt = bt.num2date(dt)
        print(f"{dt.isoformat()} - {txt}")

    def notify_order(self, order):
        # called on order status changes
        if order.status in [order.Submitted, order.Accepted]:
            return  # no action yet

        dt = self.data.datetime[0]
        dt = bt.num2date(dt)
        if order.status in [order.Completed]:
            side = "BUY " if order.isbuy() else "SELL"
            exec_price = order.executed.price
            size       = order.executed.size
            cost       = order.executed.value
            self.log(f"{side} EXECUTED, Price: {exec_price:.2f}, Size: {size:.0f}, Cost: {cost:.2f}", dt)
        elif order.status in [order.Canceled, order.Rejected]:
            self.log("Order Canceled/Rejected", dt)

        # reset
        self.order = None

    def next(self):
        # nothing pending
        if self.order:
            return

        pos = self.position.size
        prev_f, prev_s = self.hma_fast[-1], self.hma_slow[-1]
        curr_f, curr_s = self.hma_fast[0],  self.hma_slow[0]

        # ENTRY
        if pos == 0 and prev_f <= prev_s and curr_f > curr_s:
            self.log("SIGNAL → BUY", self.data.datetime[0])
            self.order = self.buy()

        elif pos == 0 and prev_f >= prev_s and curr_f < curr_s:
            self.log("SIGNAL → SELL", self.data.datetime[0])
            self.order = self.sell()

        # EXIT LONG
        elif pos > 0 and curr_f < curr_s:
            self.log("SIGNAL → EXIT LONG", self.data.datetime[0])
            self.order = self.close()

        # EXIT SHORT
        elif pos < 0 and curr_f > curr_s:
            self.log("SIGNAL → EXIT SHORT", self.data.datetime[0])
            self.order = self.close()

    def stop(self):
        pnl = round(self.broker.getvalue() - self.broker.startingcash, 2)
        self.log(f"END PnL: {pnl}", self.data.datetime[0])
