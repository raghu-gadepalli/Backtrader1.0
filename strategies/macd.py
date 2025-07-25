import backtrader as bt
from collections import defaultdict
from datetime import datetime


class MACDHist(bt.Indicator):
    """
    Convenience wrapper that exposes MACD, signal and histogram (macd - signal)
    as .macd, .signal and .hist lines.
    """
    lines = ("macd", "signal", "hist")
    params = dict(fast=120, slow=240, signal=60)

    def __init__(self):
        macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.p.fast,
            period_me2=self.p.slow,
            period_signal=self.p.signal,
        )
        self.lines.macd   = macd.macd
        self.lines.signal = macd.signal
        self.lines.hist   = macd.macd - macd.signal


class MACDStrategy(bt.Strategy):
    """
    SuperTrend-style MACD strategy.

    Entry rules
    -----------
     Long  when  macd crosses ABOVE signal AND hist > +hist_thresh
     Short when  macd crosses BELOW signal AND hist < -hist_thresh

    Exit / reverse rules
    --------------------
     If long and a short signal fires -> close (and reverse if allow_reverse=True)
     If short and a long  signal fires -> close (and reverse if allow_reverse=True)

    Other
    -----
     Ignores bars before `eval_start`
     Snapshots ATR/Close on entry for analyzers (atr_entry / atr_pct, etc.)
     Optionally keeps MAE/MFE updated while trades are open (record_mae_mfe=True)
    """
    params = dict(
        fast=120,
        slow=240,
        signal=60,
        hist_thresh=0.00075,
        eval_start=None,         # datetime or None
        allow_reverse=True,      # open opposite side immediately
        record_mae_mfe=True,     # keep updating MAE/MFE intratrade (for TradeList-like analyzers)
    )

    def __init__(self):
        # Indicators
        self.macd  = MACDHist(self.data, fast=self.p.fast, slow=self.p.slow, signal=self.p.signal)
        self.xover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)
        self.atr14 = bt.indicators.ATR(self.data, period=14)

        # Entry-snapshot vars (for analyzers)
        self.last_atr_on_entry   = None
        self.last_close_on_entry = None

        # For tracking MAE/MFE etc., keyed by tradeid
        self._open_stats = defaultdict(dict)

    # ---------- Helpers -----------------------------------------------------
    def _snap_entry(self):
        self.last_atr_on_entry   = float(self.atr14[0])
        self.last_close_on_entry = float(self.data.close[0])

    def _update_mae_mfe(self):
        """Update MAE/MFE for the currently open trade (if any)."""
        if not self.p.record_mae_mfe:
            return
        # Backtrader only allows a single net position; use broker position info
        pos_size = self.position.size
        if pos_size == 0:
            return

        price = float(self.data.close[0])

        # try to find the only open tradeid we track
        for tid, st in self._open_stats.items():
            if st.get("is_open", False):
                entry_px = st.get("entry_px", 0.0)
                if pos_size > 0:  # long
                    diff = price - entry_px
                    st["mae_abs"] = min(st.get("mae_abs", 0.0), diff) if "mae_abs" in st else diff
                    st["mfe_abs"] = max(st.get("mfe_abs", 0.0), diff) if "mfe_abs" in st else diff
                else:             # short
                    diff = entry_px - price
                    st["mae_abs"] = min(st.get("mae_abs", 0.0), diff) if "mae_abs" in st else diff
                    st["mfe_abs"] = max(st.get("mfe_abs", 0.0), diff) if "mfe_abs" in st else diff
                break

    # ---------- Core logic --------------------------------------------------
    def next(self):
        # Skip bars before evaluation start
        if self.p.eval_start:
            dt: datetime = self.data.datetime.datetime(0)
            if dt < self.p.eval_start:
                return

        hist = float(self.macd.hist[0])

        long_sig  = (self.xover > 0) and (hist >  self.p.hist_thresh)
        short_sig = (self.xover < 0) and (hist < -self.p.hist_thresh)

        # Update MAE/MFE for any open trade
        self._update_mae_mfe()

        if not self.position:
            if long_sig:
                self._snap_entry()
                self.buy()
            elif short_sig:
                self._snap_entry()
                self.sell()
            return

        # We have a position
        if self.position.size > 0:  # long
            if short_sig:
                # reverse or just exit
                self.close()
                if self.p.allow_reverse:
                    self._snap_entry()
                    self.sell()
        else:  # short
            if long_sig:
                self.close()
                if self.p.allow_reverse:
                    self._snap_entry()
                    self.buy()

    # ---------- Notifications ----------------------------------------------
    def notify_trade(self, trade):
        tid = trade.tradeid

        if trade.isopen:
            # Initialize tracking
            self._open_stats[tid]["entry_px"] = trade.price
            self._open_stats[tid]["size"]     = trade.size
            self._open_stats[tid]["is_long"]  = (trade.size > 0)
            self._open_stats[tid]["atr_entry"] = self.last_atr_on_entry
            self._open_stats[tid]["close_entry"] = self.last_close_on_entry
            self._open_stats[tid]["mae_abs"] = 0.0
            self._open_stats[tid]["mfe_abs"] = 0.0
            self._open_stats[tid]["is_open"] = True
            return

        if not trade.isclosed:
            return

        # Finalize
        self._open_stats[tid]["is_open"] = False
        # Nothing else to do here if your TradeList analyzer
        # reads directly from trade.history or calculates on its own.

    def notify_order(self, order):
        # Keep identical to ST (only act on completion if needed)
        if order.status not in [order.Completed, order.Canceled, order.Rejected]:
            return
