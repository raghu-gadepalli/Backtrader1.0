# analyzers/trade_list.py
import backtrader as bt
from collections import defaultdict

class TradeList(bt.Analyzer):
    """
    Robust trade log with ATR, MAE/MFE and percentages.

    Strategy MUST set right before entry order:
        self.last_atr_on_entry
        self.last_close_on_entry
    """

    def start(self):
        self.rows = []
        # track running MAE/MFE per tradeid while trade is open
        self._open_stats = defaultdict(lambda: {"entry_px": None,
                                                "size": None,
                                                "mae_abs": 0.0,
                                                "mfe_abs": 0.0,
                                                "is_long": True})

    # ───────── helpers ─────────
    @staticmethod
    def _entry_from_hist(hist, trade):
        if hist:
            h0 = hist[0]
            px = getattr(h0.event, 'price', None)
            sz = getattr(h0.event, 'size',  None)
            if px is not None and sz is not None and sz != 0:
                return float(px), float(sz)
        # fallback
        return float(trade.price), float(trade.size or 0.0)

    @staticmethod
    def _exit_from_hist(hist, trade, entry_px, entry_sz):
        if hist:
            hL = hist[-1]
            px = getattr(hL.event,  'price', None)
            if px is None:
                px = getattr(hL.status, 'price', None)
            if px is not None:
                return float(px)
        # fallback algebra
        if entry_sz:
            return float(entry_px + (trade.pnl / entry_sz))
        return float(entry_px)

    # ───────── analyzer hooks ─────────
    def notify_trade(self, trade):
        tid = trade.tradeid

        if trade.isopen:
            # initialise tracking
            entry_px = trade.price
            size     = trade.size
            self._open_stats[tid]["entry_px"] = entry_px
            self._open_stats[tid]["size"]     = size
            self._open_stats[tid]["is_long"]  = (size > 0)
            # atr snapshot already put by strategy
            return

        if not trade.isclosed:
            return

        # closed: finalize row
        hist = trade.history or []
        entry_px, size = self._entry_from_hist(hist, trade)
        exit_px        = self._exit_from_hist(hist, trade, entry_px, size)

        # if still 0, try last stored size
        if size == 0:
            size = float(self._open_stats[tid]["size"] or 0.0)

        mae_abs = self._open_stats[tid]["mae_abs"]
        mfe_abs = self._open_stats[tid]["mfe_abs"]

        notional = entry_px * abs(size)
        mae_pct  = (mae_abs / notional) if notional else 0.0
        mfe_pct  = (mfe_abs / notional) if notional else 0.0
        ret_pct  = (float(trade.pnlcomm) / notional) if notional else 0.0

        strat   = self.strategy
        atr_e   = getattr(strat, "last_atr_on_entry", None)
        close_e = getattr(strat, "last_close_on_entry", None)
        atr_pct = (atr_e / close_e) if (atr_e is not None and close_e) else None

        self.rows.append(dict(
            dt_in     = bt.num2date(trade.dtopen),
            dt_out    = bt.num2date(trade.dtclose),
            price_in  = entry_px,
            price_out = exit_px,
            size      = float(size),
            pnl       = float(trade.pnl),
            pnl_comm  = float(trade.pnlcomm),
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
        Called every bar. Update MAE/MFE for any open trades using current H/L.
        """
        if not self._open_stats:
            return

        data = self.strategy.data
        hi   = float(data.high[0])
        lo   = float(data.low[0])

        # there can be multiple overlapping trades only with multiple datas;
        # with one data, tradeid increments and at most 1 open. We'll just loop anyway.
        for tid, st in self._open_stats.items():
            ep   = st["entry_px"]
            if ep is None:
                continue
            if st["is_long"]:
                dd = max(0.0, ep - lo)   # adverse move
                ff = max(0.0, hi - ep)   # favourable move
            else:
                dd = max(0.0, hi - ep)
                ff = max(0.0, ep - lo)

            if dd > st["mae_abs"]:
                st["mae_abs"] = dd
            if ff > st["mfe_abs"]:
                st["mfe_abs"] = ff

    def get_analysis(self):
        return self.rows
