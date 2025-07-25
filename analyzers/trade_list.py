import backtrader as bt
from collections import defaultdict

class TradeList(bt.Analyzer):
    """
    Captures every trade (open and closed) with full fields:
    - Keys on trade.tradeid so open/close see the same entry.
    - Records dt_in on open.
    - Captures atr_entry instantly (from strategy.last_atr_on_entry).
    - On close, fills dt_out, computes atr_pct, barlen, exit_type.
    - Maintains MAE/MFE in next().
    """

    def start(self):
        super().start()
        self.closed_trades = []
        # map tradeid -> stats dict
        self.open_stats    = {}
    
    @staticmethod
    def _safe(v):
        try:
            return float(v)
        except:
            return None

    def notify_trade(self, trade):
        # Use trade.tradeid as the key
        tid = trade.tradeid

        # ─── on open ────────────────────────────────────
        if trade.isopen:
            stats = {
                'tradeid':    tid,
                'symbol':     trade.data._name,
                'dt_in':      bt.num2date(trade.dtopen).isoformat(),
                'price_in':   self._safe(trade.price),
                'size':       self._safe(trade.size),
                'entry_bar':  len(self.strategy),
                'atr_entry':  getattr(self.strategy, 'last_atr_on_entry', None),
                'pnl_comm':   None,
                'atr_pct':    None,
                'mae_abs':    0.0,
                'mfe_abs':    0.0,
            }
            self.open_stats[tid] = stats
            return

        # ─── on close ───────────────────────────────────
        if trade.isclosed:
            stats = self.open_stats.pop(tid, None)
            if stats is None:
                return  # no matching open → skip

            # 1) Prefer the tagged exit_type if present
            exit_type = getattr(trade, '_exit_type', None)

            # 2) Otherwise fall back to history or default to SIGNAL
            if not exit_type:
                for h in reversed(getattr(trade, 'history', []) or []):
                    et = getattr(h.event, 'exectype', None)
                    if et == bt.Order.Stop:
                        exit_type = 'STOPLOSS'; break
                    if et == bt.Order.StopTrail:
                        exit_type = 'TRAIL';    break
                    if et == bt.Order.Limit:
                        exit_type = 'TARGET';   break
                exit_type = exit_type or 'SIGNAL'

            # Find exit price
            exit_px = None
            for h in reversed(getattr(trade, 'history', []) or []):
                ev = getattr(h, 'event', None)
                if ev and hasattr(ev, 'price'):
                    exit_px = self._safe(ev.price)
                    break
            if exit_px is None:
                exit_px = getattr(trade, 'priceclose', None) or self._safe(trade.price)

            # Compute core metrics
            entry_px  = stats['price_in']
            size      = stats['size']
            pnl       = self._safe(trade.pnl)
            pnl_comm  = self._safe(trade.pnlcomm)
            atr_entry = stats['atr_entry']
            atr_pct   = (atr_entry / entry_px) if (entry_px and atr_entry) else None
            barlen    = len(self.strategy) - stats['entry_bar']

            # Build the record
            rec = {
                'dt_in':        stats['dt_in'],
                'dt_out':       bt.num2date(trade.dtclose).isoformat(),
                'price_in':     entry_px,
                'price_out':    exit_px,
                'size':         size,
                'side':         'BUY' if size > 0 else 'SELL',
                'pnl':          pnl,
                'pnl_comm':     pnl_comm,
                'barlen':       barlen,
                'tradeid':      tid,
                'atr_entry':    atr_entry,
                'atr_pct':      atr_pct,
                'mae_abs':      stats['mae_abs'],
                'mfe_abs':      stats['mfe_abs'],
                'exit_type':    exit_type,
                'symbol':       stats['symbol'],
                'ignore_before':getattr(self.strategy.p, 'ignore_before', None),

                # strategy params
                'fast':            self.strategy.p.fast,
                'mid1':            self.strategy.p.mid1,
                'mid2':            self.strategy.p.mid2,
                'mid3':            self.strategy.p.mid3,
                'adx_period':      self.strategy.p.adx_period,
                'adx_threshold':   self.strategy.p.adx_threshold,
                'atr_period':      self.strategy.p.atr_period,
                'atr_mult':        self.strategy.p.atr_mult,
                'sl_mode':         self.strategy.p.sl_mode,
                'sl_value':        self.strategy.p.sl_value,
                'use_sl_tg':       self.strategy.p.use_sl_tg,
                'use_trailing':    self.strategy.p.use_trailing,
                'trail_atr_mult':  self.strategy.p.trail_atr_mult,
                'use_signal_exit': self.strategy.p.use_signal_exit,
                'reentry_cooldown':self.strategy.p.reentry_cooldown,

                # profit-target params
                'tg_mode':         self.strategy.p.tg_mode,
                'tg1':             self.strategy.p.tg1,
                'tg2':             self.strategy.p.tg2,
                'tg3':             self.strategy.p.tg3,
            }
            self.closed_trades.append(rec)

    def next(self):
        hi = self._safe(self.strategy.data.high[0])
        lo = self._safe(self.strategy.data.low[0])
        for stats in self.open_stats.values():
            ep = stats.get('price_in')
            if ep is None:
                continue
            size    = stats['size']
            is_long = size > 0
            adverse = (ep - lo) if is_long else (hi - ep)
            fav     = (hi - ep) if is_long else (ep - lo)
            stats['mae_abs'] = max(stats['mae_abs'], adverse)
            stats['mfe_abs'] = max(stats['mfe_abs'], fav)

    def get_analysis(self):
        # 1) closed trades first
        results = list(self.closed_trades)

        # 2) then open trades
        for stats in self.open_stats.values():
            entry = stats['price_in']
            last  = self._safe(self.strategy.data.close[0]) if entry is not None else None
            pnl   = ((last - entry) * stats['size']) if (entry is not None and last is not None) else None
            barlen= len(self.strategy) - stats['entry_bar']
            rec = {
                'dt_in':        stats['dt_in'],
                'dt_out':       None,
                'price_in':     entry,
                'price_out':    last,
                'size':         stats['size'],
                'side':         'BUY' if stats['size']>0 else 'SELL',
                'pnl':          pnl,
                'pnl_comm':     0.0,
                'barlen':       barlen,
                'tradeid':      stats['tradeid'],
                'atr_entry':    stats['atr_entry'],
                'atr_pct':      (stats['atr_entry']/entry) if (stats['atr_entry'] and entry) else None,
                'mae_abs':      stats['mae_abs'],
                'mfe_abs':      stats['mfe_abs'],
                'exit_type':    'OPEN',
                'symbol':       stats['symbol'],
                'ignore_before':getattr(self.strategy.p, 'ignore_before', None),

                # same params as above...
                **{k: getattr(self.strategy.p, k) for k in (
                   'fast','mid1','mid2','mid3',
                   'adx_period','adx_threshold',
                   'atr_period','atr_mult',
                   'sl_mode','sl_value',
                   'use_sl_tg','use_trailing','trail_atr_mult',
                   'use_signal_exit','reentry_cooldown',
                   'tg_mode','tg1','tg2','tg3'
                )}
            }
            results.append(rec)

        return results
