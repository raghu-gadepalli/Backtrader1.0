import backtrader as bt

class HmaLevel3Strategy(bt.Strategy):
    params = dict(
        fast=200,        # HMA fast
        mid1=320,        # HMA “level-3” (320)
        atr_period=14,   # ATR length (optional noise filter)
        atr_mult=0.0,    # set >0 to gate by gap > ATR×mult
        printlog=True,   # turn on/off console prints
    )

    def __init__(self):
        price        = self.data.close
        # fast and “level-3” HMAs
        self.hma_fast = bt.indicators.HullMovingAverage(
            price, period=self.p.fast, plotname=f"HMA_FAST({self.p.fast})"
        )
        self.hma_mid1 = bt.indicators.HullMovingAverage(
            price, period=self.p.mid1, plotname=f"HMA_MID1({self.p.mid1})"
        )
        # ATR for optional gating
        self.atr       = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.order     = None

    def log(self, txt):
        if not self.p.printlog:
            return
        dt = bt.num2date(self.data.datetime[0])
        print(f"{dt.isoformat()} — {txt}")

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status == order.Completed:
            side = "BUY " if order.isbuy() else "SELL"
            self.log(f"{side}EXECUTED @ {order.executed.price:.2f}")
        self.order = None

    def next(self):
        # skip if pending order
        if self.order:
            return

        prev_f, prev_m = self.hma_fast[-1], self.hma_mid1[-1]
        curr_f, curr_m = self.hma_fast[0],  self.hma_mid1[0]
        gap    = abs(curr_f - curr_m)
        thresh = self.p.atr_mult * self.atr[0]
        pos    = self.position.size

        # → BUY when fast crosses above mid1
        if pos == 0 and prev_f <= prev_m and curr_f > curr_m and gap > thresh:
            self.log(f"SIGNAL → BUY (gap {gap:.2f} > {thresh:.2f})")
            self.order = self.buy()

        # → SELL when fast crosses below mid1
        elif pos == 0 and prev_f >= prev_m and curr_f < curr_m and gap > thresh:
            self.log(f"SIGNAL → SELL (gap {gap:.2f} > {thresh:.2f})")
            self.order = self.sell()

        # EXIT LONG
        elif pos > 0 and curr_f < curr_m:
            self.log("SIGNAL → EXIT LONG")
            self.order = self.close()

        # EXIT SHORT
        elif pos < 0 and curr_f > curr_m:
            self.log("SIGNAL → EXIT SHORT")
            self.order = self.close()

    def stop(self):
        pnl = self.broker.getvalue() - self.broker.startingcash
        self.log(f"END PnL: {pnl:.2f}")
