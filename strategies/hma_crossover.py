# strategies/hma_crossover.py
import backtrader as bt


class HmaCrossover(bt.Strategy):
    """
    Fast/slow HMA crossover.
    - Uses ATR (period=atr_period) only to record atr_entry for trades (no gap filter unless you set atr_mult > 0).
    - Blocks signals before eval_start (like SuperTrend runner).
    """
    params = dict(
        fast=60,
        slow=90,
        atr_period=14,
        atr_mult=0.0,          # set >0 if you want a gap filter; 0 disables it
        eval_start=None,       # datetime; strategy ignores entries before this
        printlog=False,
    )

    def log(self, txt):
        if self.p.printlog:
            dt = bt.num2date(self.data.datetime[0]).isoformat()
            print(f"{dt} {txt}")

    def __init__(self):
        price = self.data.close

        self.hma_fast = bt.indicators.HullMovingAverage(price, period=self.p.fast,
                                                        plotname=f"HMA_FAST({self.p.fast})")
        self.hma_slow = bt.indicators.HullMovingAverage(price, period=self.p.slow,
                                                        plotname=f"HMA_SLOW({self.p.slow})")
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)

        self._order    = None
        self._prev_rel = None      # fast > slow on previous bar?
        # fields well stash for TradeList (just like SuperTrend)
        self.last_atr_on_entry   = None
        self.last_close_on_entry = None

    #  events 
    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self.log(f"{side} EXECUTED @ {order.executed.price:.2f} size {order.executed.size}")
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            self.log("Order Canceled/Margin/Rejected")
        self._order = None

    def notify_trade(self, trade):
        # Optional prints
        if trade.isclosed:
            self.log(f"TRADE CLOSED PnL {trade.pnl:.2f} (Net {trade.pnlcomm:.2f})")

    #  core 
    def next(self):
        if self._order:
            return

        dt = self.data.datetime.datetime(0)
        if self.p.eval_start and dt < self.p.eval_start:
            # ignore signals; let indicators warm
            return

        f0, s0 = float(self.hma_fast[0]), float(self.hma_slow[0])
        f1, s1 = float(self.hma_fast[-1]), float(self.hma_slow[-1])

        rel_prev = f1 > s1
        rel_now  = f0 > s0

        if self._prev_rel is None:
            self._prev_rel = rel_now
            return

        gap_ok = True
        if self.p.atr_mult > 0:
            gap_ok = abs(f0 - s0) > self.p.atr_mult * float(self.atr[0])

        pos_sz = self.position.size

        # LONG entry
        if pos_sz == 0 and (not rel_prev) and rel_now and gap_ok:
            self.last_atr_on_entry   = float(self.atr[0])
            self.last_close_on_entry = float(self.data.close[0])
            self._order = self.buy()

        # SHORT entry
        elif pos_sz == 0 and rel_prev and (not rel_now) and gap_ok:
            self.last_atr_on_entry   = float(self.atr[0])
            self.last_close_on_entry = float(self.data.close[0])
            self._order = self.sell()

        # EXITs: opposite cross
        elif pos_sz > 0 and not rel_now:
            self._order = self.close()
        elif pos_sz < 0 and rel_now:
            self._order = self.close()

        self._prev_rel = rel_now

    def stop(self):
        pnl = self.broker.getvalue() - self.broker.startingcash
        self.log(f"END PnL: {pnl:.2f}")
