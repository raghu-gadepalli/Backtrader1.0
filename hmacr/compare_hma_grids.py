#!/usr/bin/env python3
# scripts/compare_hma_grids.py

import itertools
import backtrader as bt
from data.load_candles    import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

#  Global settings 
WARMUP_START = "2025-04-01"
END          = "2025-07-06"
ATR_MULT     = 0.0

#  Fixed ICICIBANK params 
ICICI = dict(fast=120, mid1=720, mid2=240, mid3=480, atr_mult=ATR_MULT)

#  Candidate grids for INFY & RELIANCE 
INFY_CANDS = {
    "60-grid": dict(fast=160, mid1=1600, mid2=320,  mid3=640,  atr_mult=ATR_MULT),
    "80-grid": dict(fast=700, mid1=560,  mid2=1400, mid3=2800, atr_mult=ATR_MULT),
}

REL_CANDS  = {
    "60-grid": dict(fast=160, mid1=1600, mid2=320,  mid3=640,  atr_mult=ATR_MULT),
    "80-grid": dict(fast=200, mid1=1040, mid2=400,  mid3=800,  atr_mult=ATR_MULT),
}

def backtest(symbol, cfg):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    df = load_candles(symbol, WARMUP_START, END)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes, compression=1)
    cerebro.adddata(data)
    cerebro.addstrategy(HmaStateStrengthStrategy, 
                        fast=cfg["fast"], mid1=cfg["mid1"],
                        mid2=cfg["mid2"], mid3=cfg["mid3"],
                        atr_mult=cfg["atr_mult"], printlog=False)

    strat = cerebro.run()[0]
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio") or float("-inf")
    tr     = strat.analyzers.trades.get_analysis()
    won    = tr.get("won",{}).get("total",0)
    lost   = tr.get("lost",{}).get("total",0)
    total  = won + lost
    wr     = won/total if total else 0.0

    return sharpe, wr, total

if __name__ == "__main__":
    print(f"{'INFY grid':<10} {'REL grid':<10}   ICICI Sharpe/WR/Trades   INFY Sharpe/WR/Trades   REL Sharpe/WR/Trades")
    print("-"*100)

    for infy_name, rel_name in itertools.product(INFY_CANDS, REL_CANDS):
        infy_cfg = INFY_CANDS[infy_name]
        rel_cfg  = REL_CANDS [rel_name]

        icici_s, icici_wr, icici_t = backtest("ICICIBANK", ICICI)
        infy_s, infy_wr, infy_t = backtest("INFY", infy_cfg)
        rel_s,  rel_wr,  rel_t  = backtest("RELIANCE", rel_cfg)

        print(f"{infy_name:<10} {rel_name:<10}   "
              f"{icici_s: .3f}/{icici_wr: .2%}/{icici_t:<5}   "
              f"{infy_s: .3f}/{infy_wr: .2%}/{infy_t:<5}   "
              f"{rel_s: .3f}/{rel_wr: .2%}/{rel_t:<5}")
