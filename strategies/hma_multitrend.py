from typing import Dict, Any, Tuple
import backtrader as bt
from config.enums import TrendType

def derive_hma_state_strength(rec: Dict[str, Any]) -> Tuple[TrendType, str]:
    h, m1, m2, m3 = rec["hma"], rec["hma_mid1"], rec["hma_mid2"], rec["hma_mid3"]
    bull3 = h > m1; bull4 = h > m2; bull5 = h > m3
    bear3 = h < m1; bear4 = h < m2; bear5 = h < m3

    if bull5 and bull4 and bull3: return TrendType.BUY,  "Strong Buy"
    if bull5 and bull4:           return TrendType.BUY,  "Medium Buy"
    if bull5 and bull3:           return TrendType.BUY,  "Weak Buy"
    if bull5:                     return TrendType.BUY,  "Very Weak Buy"

    if bear5 and bear4 and bear3: return TrendType.SELL, "Strong Sell"
    if bear5 and bear4:           return TrendType.SELL, "Medium Sell"
    if bear5 and bear3:           return TrendType.SELL, "Weak Sell"
    if bear5:                     return TrendType.SELL, "Very Weak Sell"

    return TrendType.NO_TREND, "Neutral"


class HmaMultiTrendStrategy(bt.Strategy):
    params = dict(
        fast=600, mid1=760, mid2=1040, mid3=1520,
        atr_period=14, atr_mult=0.1,
        adx_period=14, adx_threshold=25.0,
        printlog=False,
    )

    def __init__(self):
        p = self.p
        c = self.data.close

        self.hma      = bt.indicators.HullMovingAverage(c, period=p.fast)
        self.hma_mid1 = bt.indicators.HullMovingAverage(c, period=p.mid1)
        self.hma_mid2 = bt.indicators.HullMovingAverage(c, period=p.mid2)
        self.hma_mid3 = bt.indicators.HullMovingAverage(c, period=p.mid3)

        self.atr = bt.indicators.ATR(self.data, period=p.atr_period)
        self.adx = bt.indicators.ADX(self.data, period=p.adx_period)

        self.order = None

        # for analyzer
        self.last_atr_on_entry   = None
        self.last_close_on_entry = None

    def log(self, msg):
        if self.p.printlog:
            dt = bt.num2date(self.data.datetime[0])
            print(f"{dt.isoformat()} {msg}")

    def next(self):
        if self.order:
            return

        rec = dict(hma=self.hma[0], hma_mid1=self.hma_mid1[0],
                   hma_mid2=self.hma_mid2[0], hma_mid3=self.hma_mid3[0])
        state, strength = derive_hma_state_strength(rec)

        gap    = abs(self.data.close[0] - self.hma[0])
        thresh = self.p.atr_mult * self.atr[0]
        adx_ok = self.adx[0] > self.p.adx_threshold
        pos    = self.position.size

        # Entries
        if pos == 0 and adx_ok and gap > thresh:
            if state == TrendType.BUY and strength in ("Strong Buy", "Medium Buy"):
                self.last_atr_on_entry   = float(self.atr[0])
                self.last_close_on_entry = float(self.data.close[0])
                self.log(f"BUY  {strength} gap {gap:.2f}>{thresh:.2f} ADX {self.adx[0]:.1f}")
                self.order = self.buy()
            elif state == TrendType.SELL and strength in ("Strong Sell", "Medium Sell"):
                self.last_atr_on_entry   = float(self.atr[0])
                self.last_close_on_entry = float(self.data.close[0])
                self.log(f"SELL {strength} gap {gap:.2f}>{thresh:.2f} ADX {self.adx[0]:.1f}")
                self.order = self.sell()

        # Exits
        elif pos > 0 and state == TrendType.SELL:
            self.log("EXIT LONG")
            self.order = self.close()
        elif pos < 0 and state == TrendType.BUY:
            self.log("EXIT SHORT")
            self.order = self.close()

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self.log(f"{side} EXECUTED @ {order.executed.price:.2f} size {order.executed.size}")
        elif order.status in (order.Canceled, order.Rejected):
            self.log("ORDER Canceled/Rejected")
        self.order = None
