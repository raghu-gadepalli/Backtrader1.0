# strategies/HmaStateStrengthStrategy.py

from typing import Dict, Any, Tuple
import backtrader as bt
from config.enums import TrendType   # adjust import as needed

def derive_hma_state_strength(rec: Dict[str, Any]) -> Tuple[TrendType, str]:
    h   = rec["hma"]
    m1  = rec["hma_mid1"]
    m2  = rec["hma_mid2"]
    m3  = rec["hma_mid3"]

    bull3 = h > m1; bull4 = h > m2; bull5 = h > m3
    bear3 = h < m1; bear4 = h < m2; bear5 = h < m3

    if bull5 and bull4 and bull3:
        return TrendType.BUY,  "Strong Buy"
    if bull5 and bull4:
        return TrendType.BUY,  "Medium Buy"
    if bull5 and bull3:
        return TrendType.BUY,  "Weak Buy"
    if bull5:
        return TrendType.BUY,  "Very Weak Buy"

    if bear5 and bear4 and bear3:
        return TrendType.SELL, "Strong Sell"
    if bear5 and bear4:
        return TrendType.SELL, "Medium Sell"
    if bear5 and bear3:
        return TrendType.SELL, "Weak Sell"
    if bear5:
        return TrendType.SELL, "Very Weak Sell"

    return TrendType.NO_TREND, "Neutral"


class HmaMultiTrendStrategy(bt.Strategy):
    params = dict(
        fast          = 600,    # tuned fast HMA
        mid1          = 760,    # tuned mid HMA #1
        mid2          = 1040,   # tuned mid HMA #2
        mid3          = 1520,   # tuned slow HMA
        atr_period    = 14,
        atr_mult      = 0.1,    # gap noise‐gate
        adx_period    = 14,     # new ADX lookback
        adx_threshold = 25.0,   # require ADX > this to trade
        printlog      = False,
    )

    def __init__(self):
        p     = self.p
        price = self.data.close

        # four HMAs
        self.hma       = bt.indicators.HullMovingAverage(price, period=p.fast)
        self.hma_mid1  = bt.indicators.HullMovingAverage(price, period=p.mid1)
        self.hma_mid2  = bt.indicators.HullMovingAverage(price, period=p.mid2)
        self.hma_mid3  = bt.indicators.HullMovingAverage(price, period=p.mid3)

        # ATR filter
        self.atr       = bt.indicators.ATR(self.data, period=p.atr_period)

        # ADX filter
        self.adx       = bt.indicators.ADX(self.data, period=p.adx_period)

        self.order     = None

    def log(self, txt, dt=None):
        if not self.p.printlog:
            return
        dt = bt.num2date(self.data.datetime[0])
        print(f"{dt.isoformat()} — {txt}")

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status == order.Completed:
            side = "BUY " if order.isbuy() else "SELL"
            self.log(f"{side}EXECUTED @ {order.executed.price:.2f}, Size {order.executed.size}")
        elif order.status in (order.Canceled, order.Rejected):
            self.log("Order Canceled/Rejected")
        self.order = None  # reset

    def next(self):
        if self.order:
            return

        # current readings
        rec = {
            "hma":       self.hma[0],
            "hma_mid1":  self.hma_mid1[0],
            "hma_mid2":  self.hma_mid2[0],
            "hma_mid3":  self.hma_mid3[0],
        }
        state, strength = derive_hma_state_strength(rec)

        gap    = abs(self.data.close[0] - self.hma[0])
        thresh = self.p.atr_mult * self.atr[0]
        adx_ok = self.adx[0] > self.p.adx_threshold
        pos    = self.position.size

        # ENTRY LONG
        if pos == 0 and state == TrendType.BUY \
           and strength in ("Strong Buy","Medium Buy") \
           and gap > thresh and adx_ok:
            self.log(f"SIGNAL → BUY ({strength}, gap {gap:.2f} > {thresh:.2f}, ADX {self.adx[0]:.1f})")
            self.order = self.buy()

        # ENTRY SHORT
        elif pos == 0 and state == TrendType.SELL \
             and strength in ("Strong Sell","Medium Sell") \
             and gap > thresh and adx_ok:
            self.log(f"SIGNAL → SELL ({strength}, gap {gap:.2f} > {thresh:.2f}, ADX {self.adx[0]:.1f})")
            self.order = self.sell()

        # EXIT LONG
        elif pos > 0 and state == TrendType.SELL:
            self.log(f"SIGNAL → EXIT LONG ({strength})")
            self.order = self.close()

        # EXIT SHORT
        elif pos < 0 and state == TrendType.BUY:
            self.log(f"SIGNAL → EXIT SHORT ({strength})")
            self.order = self.close()
