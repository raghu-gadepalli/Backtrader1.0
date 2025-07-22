# analyzers/trade_list.py
import backtrader as bt
from collections import defaultdict

class TradeList(bt.Analyzer):
    """
    Robust trade log with ATR, MAE/MFE and percentages.

    Your Strategy MUST set (just before placing the entry order):
        self.last_atr_on_entry
        self.last_close_on_entry
    """

    def start(self):
        self.rows = []
        self._trade_counter = 0

        # Track open trade stats for MAE/MFE etc.
        self._open_stats = defaultdict(lambda: {
            "entry_px": None,
            "size": None,
            "mae_abs": 0.0,
            "mfe_abs": 0.0,
            "is_long": True,
        })

    # ------------- helpers -------------
    @staticmethod
    def _safe_float(v, default=0.0):
        try:
            return float(v)
        except Exception:
            return default

    def _extract_entry_exit_from_history(self, trade, entry_px, size):
        """
        Try to read entry/exit from trade.history if available.
        Returns (entry_px, size, exit_px) – any may be None if not found.
        """
        hist = getattr(trade, "history", None) or []
        if not hist:
            return entry_px, size, None

        e_px = entry_px
        e_sz = size
        x_px = None

        # First non-zero size event => entry
        for h in hist:
            ev = getattr(h, "event", None)
            if ev and getattr(ev, "size", 0):
                e_px = self._safe_float(getattr(ev, "price", e_px), e_px)
                e_sz = self._safe_float(getattr(ev, "size", e_sz), e_sz)
                break

        # Last price we can see => exit
        for h in reversed(hist):
            ev = getattr(h, "event", None)
            if ev and getattr(ev, "price", None) is not None:
                x_px = self._safe_float(ev.price, x_px)
                break
            st = getattr(h, "status", None)
            if st and getattr(st, "price", None) is not None:
                x_px = self._safe_float(st.price, x_px)
                break

        return e_px, e_sz, x_px

    # ------------- analyzer hooks -------------
    def notify_trade(self, trade):
        # tradeid can be None -> assign our own
        if getattr(trade, "tradeid", None) is not None:
            tid = trade.tradeid
        else:
            tid = id(trade)

        if trade.isopen:
            # Capture basics right away
            entry_px = self._safe_float(trade.price)
            size     = self._safe_float(trade.size)
            self._open_stats[tid]["entry_px"] = entry_px
            self._open_stats[tid]["size"]     = size
            self._open_stats[tid]["is_long"]  = (size > 0)
            return

        if not trade.isclosed:
            return

        # Closed -> finalize row
        st = self._open_stats.get(tid, {})
        entry_px = self._safe_float(st.get("entry_px", trade.price))
        size     = self._safe_float(st.get("size", trade.size))

        # Try to get better values from history
        entry_px, size, exit_px_hist = self._extract_entry_exit_from_history(trade, entry_px, size)

        # Fallback exit price if needed
        if exit_px_hist is None:
            if size:
                exit_px_hist = entry_px + (self._safe_float(trade.pnl) / size)
            else:
                exit_px_hist = entry_px

        mae_abs = self._safe_float(st.get("mae_abs", 0.0))
        mfe_abs = self._safe_float(st.get("mfe_abs", 0.0))

        notional = entry_px * abs(size) if entry_px else 0.0
        mae_pct  = (mae_abs / notional) if notional else 0.0
        mfe_pct  = (mfe_abs / notional) if notional else 0.0
        ret_pct  = (self._safe_float(trade.pnlcomm) / notional) if notional else 0.0

        strat   = self.strategy
        atr_e   = getattr(strat, "last_atr_on_entry", None)
        close_e = getattr(strat, "last_close_on_entry", None)
        atr_pct = (atr_e / close_e) if (atr_e is not None and close_e) else None

        qty  = float(size)
        side = "BUY" if qty > 0 else "SELL" if qty < 0 else "FLAT"

        self.rows.append(dict(
            dt_in     = bt.num2date(trade.dtopen),
            dt_out    = bt.num2date(trade.dtclose),
            price_in  = entry_px,
            price_out = exit_px_hist,
            size      = size,
            side      = side, 
            pnl       = self._safe_float(trade.pnl),
            pnl_comm  = self._safe_float(trade.pnlcomm),
            barlen    = trade.barlen,
            tradeid   = tid,
            atr_entry = float(atr_e) if atr_e is not None else None,
            atr_pct   = float(atr_pct) if atr_pct is not None else None,
            mae_abs   = mae_abs,
            mae_pct   = mae_pct,
            mfe_abs   = mfe_abs,
            mfe_pct   = mfe_pct,
            ret_pct   = ret_pct,
        ))

        # cleanup
        self._open_stats.pop(tid, None)

    def next(self):
        """
        Update MAE/MFE for all open trades using current bar H/L.
        """
        if not self._open_stats:
            return

        data = self.strategy.data
        hi   = self._safe_float(data.high[0])
        lo   = self._safe_float(data.low[0])

        for tid, st in self._open_stats.items():
            ep = st["entry_px"]
            if ep is None:
                continue

            if st["is_long"]:
                dd = max(0.0, ep - lo)  # adverse
                ff = max(0.0, hi - ep)  # favourable
            else:
                dd = max(0.0, hi - ep)
                ff = max(0.0, ep - lo)

            if dd > st["mae_abs"]:
                st["mae_abs"] = dd
            if ff > st["mfe_abs"]:
                st["mfe_abs"] = ff

    def get_analysis(self):
        return self.rows
