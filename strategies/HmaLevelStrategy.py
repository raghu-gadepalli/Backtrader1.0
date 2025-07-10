# strategies/HmaLevelStrategy.py

import backtrader as bt
from enum import Enum

class TrendType(Enum):
    NO_TREND = 0
    BUY     = 1
    SELL    = -1

def derive_hma_state_strength(rec):
    """
    Given a dict with keys "hma", "hma320", "hma1200", "hma3800",
    return (TrendType, strength_label).
    """
    h   = rec["hma"]
    hd  = rec["hma320"]
    he  = rec["hma1200"]
    hf  = rec["hma3800"]

    # not enough data yet
    if any(v is None for v in (h, hd, he, hf)):
        return TrendType.NO_TREND, "Neutral"

    bull3 = h > hd
    bull4 = h > he
    bull5 = h > hf
    bear3 = h < hd
    bear4 = h < he
    bear5 = h < hf

    # Buys
    if bull5 and bull4 and bull3:
        return TrendType.BUY,  "Strong Buy"
    if bull5 and bull4:
        return TrendType.BUY,  "Medium Buy"
    if bull5 and bull3:
        return TrendType.BUY,  "Weak Buy"
    if bull5:
        return TrendType.BUY,  "Very Weak Buy"

    # Sells
    if bear5 and bear4 and bear3:
        return TrendType.SELL, "Strong Sell"
    if bear5 and bear4:
        return TrendType.SELL, "Medium Sell"
    if bear5 and bear3:
        return TrendType.SELL, "Weak Sell"
    if bear5:
        return TrendType.SELL, "Very Weak Sell"

    return TrendType.NO_TREND, "Neutral"


class HmaLevelStrategy(bt.Strategy):
    params = dict(
        fast       = 200,     # HMA fast period
        mid1       = 320,     # HMA level-3
        mid2       = 1200,    # HMA level-4
        mid3       = 3800,    # HMA level-5
        atr_period = 14,
        atr_mult   = 1.0,     # require gap > atr_mult × ATR
        printlog   = False,
    )

    def __init__(self):
        price = self.data.close

        # 4 HMAs
        self.hma      = bt.indicators.HullMovingAverage(price, period=self.p.fast, plotname=f"HMA_FAST({self.p.fast})")
        self.hma320   = bt.indicators.HullMovingAverage(price, period=self.p.mid1, plotname=f"HMA_320({self.p.mid1})")
        self.hma1200  = bt.indicators.HullMovingAverage(price, period=self.p.mid2, plotname=f"HMA_1200({self.p.mid2})")
        self.hma3800  = bt.indicators.HullMovingAverage(price, period=self.p.mid3, plotname=f"HMA_3800({self.p.mid3})")

        # ATR filter
        self.atr      = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.order    = None

    def log(self, txt, dt=None):
        if not self.p.printlog:
            return
        dt0 = self.data.datetime[0]
        dt  = bt.num2date(dt0)
        print(f"{dt.isoformat()} — {txt}")

    def notify_order(self, order):
        # called on order submission/completion
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status == order.Completed:
            side = "BUY " if order.isbuy() else "SELL"
            p    = order.executed.price
            sz   = order.executed.size
            self.log(f"{side}EXECUTED @ {p:.2f}, Size {sz}")
        elif order.status in (order.Canceled, order.Rejected):
            self.log("Order Canceled/Rejected")
        # free to send next
        self.order = None

    def next(self):
        # skip if pending order
        if self.order:
            return

        # build the record for state derivation
        rec = {
            "hma":      self.hma[0],
            "hma320":   self.hma320[0],
            "hma1200":  self.hma1200[0],
            "hma3800":  self.hma3800[0],
        }
        state, strength = derive_hma_state_strength(rec)

        gap    = abs(self.data.close[0] - self.hma[0])
        thresh = self.p.atr_mult * self.atr[0]
        pos    = self.position.size

        # ENTRY LONG
        if pos == 0 and state == TrendType.BUY and strength in ("Strong Buy", "Medium Buy") and gap > thresh:
            self.log(f"SIGNAL → BUY ({strength}, gap {gap:.2f} > {thresh:.2f})")
            self.order = self.buy()

        # ENTRY SHORT
        elif pos == 0 and state == TrendType.SELL and strength in ("Strong Sell", "Medium Sell") and gap > thresh:
            self.log(f"SIGNAL → SELL ({strength}, gap {gap:.2f} > {thresh:.2f})")
            self.order = self.sell()

        # EXIT LONG
        elif pos > 0 and state == TrendType.SELL:
            self.log("SIGNAL → EXIT LONG")
            self.order = self.close()

        # EXIT SHORT
        elif pos < 0 and state == TrendType.BUY:
            self.log("SIGNAL → EXIT SHORT")
            self.order = self.close()

    def stop(self):
        # ensure any open pos is closed so analyzers count it
        if self.position:
            if self.position.size > 0:
                self.close()
            else:
                self.close()
        pnl = self.broker.getvalue() - self.broker.startingcash
        self.log(f"END PnL: {pnl:.2f}")
