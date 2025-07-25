import backtrader as bt
from collections import defaultdict

class TradeList(bt.Analyzer):
    """
    Robust trade log capturing closed and open trades with detailed stats.
    Closed trades include exit_type, pnl, pnl_comm, MAE, MFE, ATR entry, etc.
    Open trades appear as exit_type='OPEN' with floating pnl.
    """
    def start(self):
        super().start()
        # List for closed trade records
        self.closed_trades = []
        # Stats for open trades keyed by tradeid
        self.open_stats = defaultdict(lambda: {
            'tradeid': None,
            'symbol': None,
            'dt_in': None,
            'price_in': None,
            'size': None,
            'mae_abs': 0.0,
            'mfe_abs': 0.0,
            'atr_entry': None,
        })

    @staticmethod
    def _safe(v):
        try:
            return float(v)
        except:
            return 0.0

    def notify_trade(self, trade):
        tid = trade.tradeid
        # On open, initialize stats
        if trade.isopen:
            stats = self.open_stats[tid]
            stats.update({
                'tradeid': tid,
                'symbol': trade.data._name,
                'dt_in': bt.num2date(trade.dtopen).isoformat(),
                'price_in': self._safe(trade.price),
                'size': self._safe(trade.size),
                'atr_entry': getattr(self.strategy, 'atr', [None]) and self._safe(self.strategy.atr[0])
            })
            return

        # On close, finalize record and remove from open_stats
        if trade.isclosed:
            stats = self.open_stats.pop(tid, {})
            entry_px = stats.get('price_in')
            size = stats.get('size', 0)
            pnl = self._safe(trade.pnl)
            pnl_comm = self._safe(trade.pnlcomm)
            notional = entry_px * abs(size) if entry_px else 0.0
            mae_abs = stats.get('mae_abs', 0.0)
            mfe_abs = stats.get('mfe_abs', 0.0)
            mae_pct = mae_abs / notional if notional else 0.0
            mfe_pct = mfe_abs / notional if notional else 0.0
            ret_pct = pnl_comm / notional if notional else 0.0
            atr_entry = stats.get('atr_entry')
            atr_pct = atr_entry / entry_px if entry_px and atr_entry is not None else None

                        # Extract exit price from history events
            exit_px = None
            for h in reversed(getattr(trade, 'history', []) or []):
                ev = getattr(h, 'event', None)
                if ev and hasattr(ev, 'price'):
                    exit_px = self._safe(ev.price)
                    break
            if exit_px is None:
                exit_px = self._safe(trade.price)

            # Determine exit type by scanning history events
            exit_type = 'SIGNAL'
            for h in reversed(getattr(trade, 'history', []) or []):
                ev = getattr(h, 'event', None)
                if ev is not None:
                    et = getattr(ev, 'exectype', None)
                    if et == bt.Order.Stop:
                        exit_type = 'STOPLOSS'
                    elif et == bt.Order.StopTrail:
                        exit_type = 'TRAIL'
                    elif et == bt.Order.Limit:
                        exit_type = 'TARGET'
                    break

            rec = {
                'dt_in':       stats.get('dt_in'),
                'dt_out':      bt.num2date(trade.dtclose).isoformat(),
                'price_in':    entry_px,
                'price_out':   exit_px,
                'size':        size,
                'side':        'BUY' if size>0 else 'SELL',
                'pnl':         pnl,
                'pnl_comm':    pnl_comm,
                'barlen':      getattr(trade, 'barlen', None),
                'tradeid':     tid,
                'atr_entry':   atr_entry,
                'atr_pct':     atr_pct,
                'mae_abs':     mae_abs,
                'mae_pct':     mae_pct,
                'mfe_abs':     mfe_abs,
                'mfe_pct':     mfe_pct,
                'ret_pct':     ret_pct,
                'exit_type':   exit_type,
                'symbol':      stats.get('symbol'),
                'atr_mean':    getattr(self.strategy, 'atr_mean', None),
                'fast':        getattr(self.strategy.p, 'fast', None),
                'mid1':        getattr(self.strategy.p, 'mid1', None),
                'mid2':        getattr(self.strategy.p, 'mid2', None),
                'mid3':        getattr(self.strategy.p, 'mid3', None),
                'sl_mode':     getattr(self.strategy.p, 'sl_mode', None),
                'sl_value':    getattr(self.strategy.p, 'sl_value', None),
                'tg_mode':     getattr(self.strategy.p, 'tg_mode', None),
                'tg1':         getattr(self.strategy.p, 'tg1', None),
                'tg2':         getattr(self.strategy.p, 'tg2', None),
                'tg3':         getattr(self.strategy.p, 'tg3', None),
                'trail_atr_mult': getattr(self.strategy.p, 'trail_atr_mult', None),
                'use_sl_tg':      getattr(self.strategy.p, 'use_sl_tg', None),
                'use_trailing':   getattr(self.strategy.p, 'use_trailing', None),
                'use_signal_exit':getattr(self.strategy.p, 'use_signal_exit', None),
                'reentry_cooldown':getattr(self.strategy.p, 'reentry_cooldown', None),
            }
            self.closed_trades.append(rec)

    def next(self):
        # Update MAE/MFE stats for open trades per bar
        hi = self._safe(self.strategy.data.high[0])
        lo = self._safe(self.strategy.data.low[0])
        for tid, stats in self.open_stats.items():
            ep = stats.get('price_in')
            if ep is None: continue
            size = stats.get('size', 0)
            is_long = size > 0
            # adverse and favorable moves
            adverse = (ep - lo) if is_long else (hi - ep)
            fav = (hi - ep) if is_long else (ep - lo)
            stats['mae_abs'] = max(stats['mae_abs'], adverse)
            stats['mfe_abs'] = max(stats['mfe_abs'], fav)

    def get_analysis(self):
        # Merge closed trades with open trades info
        results = list(self.closed_trades)
        for tid, stats in self.open_stats.items():
            size = stats.get('size', 0)
            last = self._safe(self.strategy.data.close[0])
            entry = stats.get('price_in', 0)
            pnl = (last - entry) * size
            rec = {
                'dt_in':       stats.get('dt_in'),
                'dt_out':      None,
                'price_in':    entry,
                'price_out':   last,
                'size':        size,
                'side':        'BUY' if size>0 else 'SELL',
                'pnl':         pnl,
                'pnl_comm':    0.0,
                'barlen':      None,
                'tradeid':     tid,
                'atr_entry':   stats.get('atr_entry'),
                'atr_pct':     None,
                'mae_abs':     stats.get('mae_abs'),
                'mae_pct':     None,
                'mfe_abs':     stats.get('mfe_abs'),
                'mfe_pct':     None,
                'ret_pct':     None,
                'exit_type':   'OPEN',
                'symbol':      stats.get('symbol'),
            }
            results.append(rec)
        return results
