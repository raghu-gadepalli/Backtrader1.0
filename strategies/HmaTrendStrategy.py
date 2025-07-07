import backtrader as bt
from datetime import datetime as _dt

class HmaTrendStrategy(bt.Strategy):
    params = (
        ("fast",     600),
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
        self.order = None

    def log(self, txt, dt=None):
        """ Logging helper that accepts both float dates and datetime objects. """
        if not self.p.printlog:
            return

        # Determine a datetime.datetime object
        if dt is None:
            dt0 = self.data.datetime[0]    # numeric float
            dt_obj = bt.num2date(dt0)
        elif isinstance(dt, _dt):
            dt_obj = dt
        else:
            # assume it's a float (Backtrader date) convertible
            dt_obj = bt.num2date(dt)

        print(f"{dt_obj.isoformat()} - {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            # Use order.executed.dt which is a float timepoint
            dt_exec = order.executed.dt
            side    = "BUY " if order.isbuy() else "SELL"
            price   = order.executed.price
            size    = order.executed.size
            cost    = order.executed.value
            self.log(
                f"{side} EXECUTED, Price: {price:.2f}, Size: {size:.0f}, Cost: {cost:.2f}",
                dt=dt_exec
            )
        elif order.status in (order.Canceled, order.Rejected):
            # fallback to bar datetime
            self.log("Order Canceled/Rejected", dt=None)

        self.order = None  # reset pending order

    def next(self):
        if self.order:
            return

        pos = self.position.size
        prev_f, prev_s = self.hma_fast[-1], self.hma_slow[-1]
        curr_f, curr_s = self.hma_fast[0],  self.hma_slow[0]

        # ENTRY
        if pos == 0:
            if prev_f <= prev_s and curr_f > curr_s:
                self.log("SIGNAL → BUY")
                self.order = self.buy()
            elif prev_f >= prev_s and curr_f < curr_s:
                self.log("SIGNAL → SELL")
                self.order = self.sell()

        # EXIT LONG
        elif pos > 0 and curr_f < curr_s:
            self.log("SIGNAL → EXIT LONG")
            self.order = self.close()

        # EXIT SHORT
        elif pos < 0 and curr_f > curr_s:
            self.log("SIGNAL → EXIT SHORT")
            self.order = self.close()

    def stop(self):
        pnl = round(self.broker.getvalue() - self.broker.startingcash, 2)
        # Use data.datetime[0] (float) to log end PnL
        self.log(f"END PnL: {pnl}", dt=self.data.datetime[0])
