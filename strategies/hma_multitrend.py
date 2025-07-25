import backtrader as bt
import pandas as pd

class HmaMultiTrendStrategy(bt.Strategy):
    params = dict(
        # Hull MA timeframes
        fast=80, mid1=220, mid2=560, mid3=1520,
        # ATR for stop‑loss and gap filter
        atr_period=14, atr_mult=1.0,
        # Date filter
        ignore_before=None,  # e.g. "2025-07-01"
        # Stop‑loss settings
        use_sl_tg=True,
        sl_mode="PCT",       # "PCT" | "ATR" | "FIXED"
        sl_value=0.5,        # pct (0.5=50%), ATR‑mult or fixed price
        # Trailing‑stop settings
        use_trailing=True,
        trail_atr_mult=1.0,
        # Signal‑exit on HMA flip
        use_signal_exit=True,
        # ADX filter
        adx_period=14,
        adx_threshold=20.0,
        # Re‑entry cooldown in bars
        reentry_cooldown=0,
        # Default order size
        order_size=1,
        # Profit‑target placeholders
        tg_mode="OFF", tg1=0.0, tg2=0.0, tg3=0.0,
    )

    def __init__(self):
        # ─── Indicators ─────────────────────────────────
        self.hma_fast = bt.indicators.HMA(self.data.close, period=self.p.fast)
        self.hma_mid1 = bt.indicators.HMA(self.data.close, period=self.p.mid1)
        self.hma_mid2 = bt.indicators.HMA(self.data.close, period=self.p.mid2)
        self.hma_mid3 = bt.indicators.HMA(self.data.close, period=self.p.mid3)
        self.atr      = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.adx      = bt.indicators.ADX(self.data, period=self.p.adx_period)

        # Will hold the ATR value exactly at entry execution
        self.last_atr_on_entry = None

        # Convert ignore_before string to datetime once
        if isinstance(self.p.ignore_before, str):
            dt = pd.to_datetime(self.p.ignore_before)
            self._ignore_before = dt.to_pydatetime()
        else:
            self._ignore_before = self.p.ignore_before

        # Internal state
        self._last_close    = None
        self.entry_order    = None
        self.sl_order       = None
        self.trail_order    = None
        self._last_tradeid  = None
        self._last_exit_bar = -float("inf")

    def log(self, txt, dt=None):
        dt = dt or bt.num2date(self.data.datetime[0])
        print(f"{dt:%Y-%m-%d %H:%M:%S}, {txt}")

    def _calc_stoploss(self, entry_price):
        mode = self.p.sl_mode.upper()
        val  = self.p.sl_value
        if mode == "PCT":
            # interpret val as percent, not fraction
            return entry_price * (1.0 - val / 100.0)
        if mode == "ATR":
            return entry_price - val * self.atr[0]
        # FIXED
        return entry_price - val

    def next(self):
        bar = len(self)
        current_dt = bt.num2date(self.data.datetime[0])

        # 1) Date filter
        if self._ignore_before and current_dt < self._ignore_before:
            self._last_close = self.data.close[0]
            return

        # 2) ADX filter
        if self.adx[0] < self.p.adx_threshold:
            self._last_close = self.data.close[0]
            return

        # 3) Skip if an entry is pending or we're in cooldown
        if self.entry_order or (bar - self._last_exit_bar) <= self.p.reentry_cooldown:
            return

        # 4) Trend conditions
        long_cond  = (self.hma_fast[0]  > self.hma_mid1[0] >
                      self.hma_mid2[0]  > self.hma_mid3[0])
        short_cond = (self.hma_fast[0]  < self.hma_mid1[0] <
                      self.hma_mid2[0]  < self.hma_mid3[0])

        # 5) Entry logic
        if not self.position and (long_cond or short_cond):
            # ATR‑gap filter
            if self.p.atr_mult and self._last_close is not None:
                gap = abs(self.data.close[0] - self._last_close)
                if gap > self.p.atr_mult * self.atr[0]:
                    self._last_close = self.data.close[0]
                    self.log("Skipped entry due to ATR gap")
                    return

            size = self.p.order_size if long_cond else -self.p.order_size
            self.entry_order = self.buy(size=size) if long_cond else self.sell(size=-size)
            side = 'BUY' if long_cond else 'SELL'
            self.log(f"Submitted {side} entry ref={self.entry_order.ref} size={abs(size)}")

        # 6) Update last_close for next bar
        self._last_close = self.data.close[0]

        # 7) Signal‑exit on HMA flip
        if self.position and self.p.use_signal_exit and (long_cond or short_cond):
            exit_long  = (self.position.size < 0 and long_cond)
            exit_short = (self.position.size > 0 and short_cond)
            if exit_long or exit_short:
                # Cancel any existing stops
                if self.sl_order:
                    self.cancel(self.sl_order)
                    self.sl_order = None
                if self.trail_order:
                    self.cancel(self.trail_order)
                    self.trail_order = None

                self.close()
                self.log(f"Signal exit for tradeid={self._last_tradeid}")

    def notify_order(self, order):
        # 1) Skip pre‑execution statuses
        if order.status in (bt.Order.Created, bt.Order.Submitted, bt.Order.Accepted):
            return

        # 2) Handle entry order lifecycle
        if self.entry_order and order.ref == self.entry_order.ref:
            if order.status == bt.Order.Completed:
                entry_price = order.executed.price

                # Capture ATR at entry
                self.last_atr_on_entry = float(self.atr[0])

                direction = 'BUY' if order.size > 0 else 'SELL'
                self.log(f"Entry EXECUTED {direction} ref={order.ref} price={entry_price:.2f}")

                # Place fixed SL if enabled
                if self.p.use_sl_tg:
                    sl_price = self._calc_stoploss(entry_price)
                    self.sl_order = self.sell(
                        exectype=bt.Order.Stop,
                        price=sl_price,
                        size=abs(order.executed.size)
                    )
                    self.log(f"Placed SL order ref={self.sl_order.ref} stop={sl_price:.2f}")

                # Place trailing SL if enabled
                if self.p.use_sl_tg and self.p.use_trailing:
                    self.trail_order = self.sell(
                        exectype=bt.Order.StopTrail,
                        trailamount=self.p.trail_atr_mult * self.atr[0],
                        size=abs(order.executed.size)
                    )
                    self.log(f"Placed TRAIL order ref={self.trail_order.ref} trailmult={self.p.trail_atr_mult}")

                # clear the entry pointer only
                self.entry_order = None

            elif order.status in (bt.Order.Canceled, bt.Order.Margin, bt.Order.Rejected):
                self.log(f"Entry order {order.ref} {order.getstatusname()}")
                self.entry_order = None

        # 3) Handle exit orders
        elif order.status == bt.Order.Completed:
            # Fixed SL hit
            if order.exectype == bt.Order.Stop and getattr(self, 'sl_order', None) and order.ref == self.sl_order.ref:
                self._last_exit_type = 'STOPLOSS'
                # cancel trailing if present
                if getattr(self, 'trail_order', None):
                    self.cancel(self.trail_order)
                    self.trail_order = None
                self.log(f"Fixed SL hit ref={order.ref}")

            # Trailing SL hit
            elif order.exectype == bt.Order.StopTrail and getattr(self, 'trail_order', None) and order.ref == self.trail_order.ref:
                self._last_exit_type = 'TRAIL'
                # cancel fixed SL if present
                if getattr(self, 'sl_order', None):
                    self.cancel(self.sl_order)
                    self.sl_order = None
                self.log(f"Trailing SL hit ref={order.ref}")

    def notify_trade(self, trade):
        # 1) On open, capture the tradeid
        if trade.isopen:
            self._last_tradeid = trade.tradeid
            self.log(f"Trade OPENED tradeid={trade.tradeid} size={trade.size} price={trade.price:.2f}")

        # 2) On close, tag the exit type and reset state
        elif trade.isclosed:
            # record exit bar for cooldown
            self._last_exit_bar = len(self)

            # determine and stamp exit_type on the Trade
            exit_type = getattr(self, '_last_exit_type', None) or 'SIGNAL'
            setattr(trade, '_exit_type', exit_type)
            # clear for next trade
            self._last_exit_type = None

            # reset ATR‑on‑entry
            self.last_atr_on_entry = None

            self.log(f"Trade CLOSED tradeid={trade.tradeid} pnl={trade.pnl:.2f} comm={trade.commission:.2f}")
