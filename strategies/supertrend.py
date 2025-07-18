import backtrader as bt

class SuperTrend(bt.Indicator):
    """
    Standard SuperTrend Indicator:
    - lines.st: the SuperTrend line  
    - lines.final_up / final_dn: the internal final bands  
    - lines.trend: +1 for uptrend, –1 for downtrend  
    """
    lines = ("st", "final_up", "final_dn", "trend")
    params = dict(period=20, multiplier=3.0)

    def __init__(self):
        # ATR and HL2
        self.atr   = bt.indicators.ATR(self.data, period=self.p.period)
        self.hl2   = (self.data.high + self.data.low) / 2.0

        # Basic Bands
        self.basic_up = self.hl2 + self.p.multiplier * self.atr
        self.basic_dn = self.hl2 - self.p.multiplier * self.atr

        # need one extra bar so ATR is valid at len == period+1
        self.addminperiod(self.p.period + 1)

    def next(self):
        l = len(self)

        # ─── Initialization ───────────────────────────────────────────────────────
        if l == self.p.period + 1:
            # On first valid ATR bar, seed both final bands = basic bands,
            # set initial trend to up (+1), and st = final_dn
            self.lines.final_up[0] = self.basic_up[0]
            self.lines.final_dn[0] = self.basic_dn[0]
            self.lines.trend[0]   = 1
            self.lines.st[0]      = self.basic_dn[0]
            return

        # ─── Compute final upper band ─────────────────────────────────────────────
        prev_fu = self.lines.final_up[-1]
        if self.basic_up[0] < prev_fu or self.data.close[-1] > prev_fu:
            self.lines.final_up[0] = self.basic_up[0]
        else:
            self.lines.final_up[0] = prev_fu

        # ─── Compute final lower band ─────────────────────────────────────────────
        prev_fd = self.lines.final_dn[-1]
        if self.basic_dn[0] > prev_fd or self.data.close[-1] < prev_fd:
            self.lines.final_dn[0] = self.basic_dn[0]
        else:
            self.lines.final_dn[0] = prev_fd

        # ─── Determine trend ──────────────────────────────────────────────────────
        # if price closes above last final_up → uptrend
        if self.data.close[0] > self.lines.final_up[-1]:
            self.lines.trend[0] = 1
        # if price closes below last final_dn → downtrend
        elif self.data.close[0] < self.lines.final_dn[-1]:
            self.lines.trend[0] = -1
        # otherwise carry forward previous trend
        else:
            self.lines.trend[0] = self.lines.trend[-1]

        # ─── Set SuperTrend line ─────────────────────────────────────────────────
        # in an uptrend, ST = final lower band; in a downtrend, ST = final upper band
        if self.lines.trend[0] > 0:
            self.lines.st[0] = self.lines.final_dn[0]
        else:
            self.lines.st[0] = self.lines.final_up[0]


class ST(bt.Strategy):
    params = dict(
        st_period=20,
        st_mult=3.0,
        eval_start=None,  # datetime to start trading
    )

    def __init__(self):
        # Attach the corrected SuperTrend indicator
        self.st = SuperTrend(
            self.data,
            period=self.p.st_period,
            multiplier=self.p.st_mult
        )
        self.prev_up = None

    def next(self):
        dt = self.data.datetime.datetime(0)

        # skip until eval_start (as before)
        if self.p.eval_start and dt < self.p.eval_start:
            return

        price  = float(self.data.close[0])
        st_val = float(self.st.st[0])
        curr_up = price > st_val

        # Initialize on first bar
        if self.prev_up is None:
            self.prev_up = curr_up
            return

        # Flip up → enter long
        if curr_up and not self.prev_up:
            # print(f"{dt}  ⬆ BUY  price={price:.2f}  st={st_val:.2f}")
            self.buy()

        # Flip down → exit
        elif not curr_up and self.prev_up:
            # print(f"{dt}  ⬇ SELL price={price:.2f}  st={st_val:.2f}")
            self.close()

        self.prev_up = curr_up
