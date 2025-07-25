# strategies/hma_switcher.py
import backtrader as bt

class HmaSwitcher(bt.Strategy):
    """
    ATR-bucket based HMA crossover switcher.
    - Chooses one (fast,slow) pair each bar from a lookup.
    - Ignores signals before eval_start (so past data is only warm-up).
    """
    params = dict(
        symbol=None,          # "INFY", "RELIANCE", ...
        pcts=None,            # {"P25":..., "P50":..., "P75":...}
        lookup=None,          # {"ATR<P25":"120x180", ...}
        eval_start=None,      # datetime.datetime; do NOT trade before this
        printlog=False,
    )

    def log(self, txt):
        if self.p.printlog:
            dt = bt.num2date(self.data.datetime[0]).isoformat()
            print(f"{dt} {txt}")

    def __init__(self):
        if not (self.p.symbol and self.p.pcts and self.p.lookup):
            raise ValueError("symbol/pcts/lookup must be provided")

        price = self.data.close

        # Pre-build all HMA pairs you might switch to
        self._hma_sets = {
            "60x90":   (bt.indicators.HullMovingAverage(price, period=60),
                        bt.indicators.HullMovingAverage(price, period=90)),
            "120x180": (bt.indicators.HullMovingAverage(price, period=120),
                        bt.indicators.HullMovingAverage(price, period=180)),
            "200x300": (bt.indicators.HullMovingAverage(price, period=200),
                        bt.indicators.HullMovingAverage(price, period=300)),
        }

        self.atr = bt.indicators.ATR(self.data, period=14)

        # Track previous relation (fast>slow) for each pair
        self._prev_rel = {k: None for k in self._hma_sets}

        self._order = None

        # For TradeList analyzer
        self.last_atr_on_entry   = None
        self.last_close_on_entry = None

    # -------- helpers --------
    def _bucket(self, atrv: float) -> str:
        p25, p50, p75 = self.p.pcts["P25"], self.p.pcts["P50"], self.p.pcts["P75"]
        if atrv < p25:  return "ATR<P25"
        if atrv < p50:  return "P25P50"
        if atrv < p75:  return "P50P75"
        return ">=P75"

    # -------- bt callbacks --------
    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self.log(f"{side} EXEC @ {order.executed.price:.2f} size {order.executed.size}")
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            self.log("Order Canceled/Margin/Rejected")
        self._order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f"TRADE CLOSED PnL {trade.pnl:.2f} (Net {trade.pnlcomm:.2f})")

    def next(self):
        if self._order:
            return

        dt = self.data.datetime.datetime(0)
        atr_now = float(self.atr[0])
        bucket  = self._bucket(atr_now)
        active_key = self.p.lookup[bucket]  # e.g. "120x180"
        fast, slow = self._hma_sets[active_key]

        f0, s0 = float(fast[0]), float(slow[0])
        f1, s1 = float(fast[-1]), float(slow[-1])

        rel_prev = f1 > s1
        rel_now  = f0 > s0

        # Initialize prev state for this pair
        if self._prev_rel[active_key] is None:
            self._prev_rel[active_key] = rel_now

        # ---- warm-up / block entries before eval_start ----
        if self.p.eval_start and dt < self.p.eval_start:
            # just keep prev_rel updated so we don't mis-detect a cross later
            self._prev_rel[active_key] = rel_now
            return

        pos_sz = self.position.size

        # LONG entry
        if pos_sz == 0 and (not rel_prev) and rel_now:
            self.last_atr_on_entry   = atr_now
            self.last_close_on_entry = float(self.data.close[0])
            self._order = self.buy()

        # SHORT entry
        elif pos_sz == 0 and rel_prev and (not rel_now):
            self.last_atr_on_entry   = atr_now
            self.last_close_on_entry = float(self.data.close[0])
            self._order = self.sell()

        # EXIT on opposite cross
        elif pos_sz > 0 and not rel_now:
            self._order = self.close()
        elif pos_sz < 0 and rel_now:
            self._order = self.close()

        self._prev_rel[active_key] = rel_now

    def stop(self):
        pnl = self.broker.getvalue() - self.broker.startingcash
        self.log(f"END PnL: {pnl:.2f}")
