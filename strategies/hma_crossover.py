# strategies/HmaTrendStrategy.py

import backtrader as bt

class HmaCrossoverStrategy(bt.Strategy):
    params = (
        ("fast",        200),
        ("slow",        300),
        ("printlog",    False),
        ("atr_period",  14),
        ("atr_mult",    1.0),   # only take crossovers if gap > atr_mult × ATR
    )

    def __init__(self):
        price = self.data.close

        # HMAs
        self.hma_fast = bt.indicators.HullMovingAverage(
            price, period=self.p.fast, plotname=f"HMA_FAST({self.p.fast})")
        self.hma_slow = bt.indicators.HullMovingAverage(
            price, period=self.p.slow, plotname=f"HMA_SLOW({self.p.slow})")

        # ATR for noise filtering
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)

        self.order = None

    def log(self, txt, dt=None):
        if not self.p.printlog:
            return
        dt0 = self.data.datetime[0]
        dt  = bt.num2date(dt0)
        print(f"{dt.isoformat()} — {txt}")

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status == order.Completed:
            side = "BUY " if order.isbuy() else "SELL"
            p    = order.executed.price
            s    = order.executed.size
            self.log(f"{side} EXECUTED @ {p:.2f}, Size {s}")
        elif order.status in (order.Canceled, order.Rejected):
            self.log("Order Canceled/Rejected")
        self.order = None

    def next(self):
        # skip if still processing an order
        if self.order:
            return

        pos = self.position.size
        prev_f = self.hma_fast[-1]
        prev_s = self.hma_slow[-1]
        curr_f = self.hma_fast[0]
        curr_s = self.hma_slow[0]

        # calculate gap and threshold
        gap = abs(curr_f - curr_s)
        thresh = self.p.atr_mult * self.atr[0]

        # ENTRY LONG
        if pos == 0 and prev_f <= prev_s and curr_f > curr_s and gap > thresh:
            self.log(f"SIGNAL → BUY (gap {gap:.2f} > {thresh:.2f})")
            self.order = self.buy()

        # ENTRY SHORT
        elif pos == 0 and prev_f >= prev_s and curr_f < curr_s and gap > thresh:
            self.log(f"SIGNAL → SELL (gap {gap:.2f} > {thresh:.2f})")
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
        pnl = self.broker.getvalue() - self.broker.startingcash
        self.log(f"END PnL: {pnl:.2f}")

