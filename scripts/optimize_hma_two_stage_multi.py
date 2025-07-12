#!/usr/bin/env python3
# scripts/optimize_hma_two_stage_multi.py

import os
import sys
import csv

# ─── PROJECT ROOT ON PATH ──────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import backtrader as bt
from data.load_candles    import load_candles
from strategies.HmaStateStrengthStrategy import HmaStateStrengthStrategy

# ─── USER PARAMETERS ──────────────────────────────────────────────────────────
# STOCKS       = ["ICICIBANK", "INFY", "RELIANCE"]  # …add more tickers here…
STOCKS       = ["INFY"]  # …add more tickers here…

WARMUP_START = "2025-04-01"
END          = "2025-07-06"
ATR_MULT     = 0.0

METRIC       = "sharpe"        # or "expectancy"

# ── choose one block ──────────────────────────────────────────────────────────
FAST_RANGE   = range(60, 961, 60)    # 60-step multiples: 60,120,…,960
MID1_RANGE   = range(120, 1921, 120) # 60-step multiples: 120,240,…,1920
# ──────────────────────────────────────────────────────────────────────────────

TOP_N        = 5                    # how many top fast/mid1 to drill

# ─── REPLACE MULTIPLIERS WITH EXPLICIT RANGES ─────────────────────────────────
MID2_RANGE   = [120, 180, 240, 360, 480]    # explicit mids to try
MID3_RANGE   = [240, 360, 480, 720, 960]    # explicit mids to try
# ──────────────────────────────────────────────────────────────────────────────


def backtest(symbol, fast, mid1, mid2, mid3, atr_mult):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Minutes, riskfreerate=0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    df = load_candles(symbol, WARMUP_START, END)
    data = bt.feeds.PandasData(dataname=df,
                               timeframe=bt.TimeFrame.Minutes,
                               compression=1)
    cerebro.adddata(data)
    cerebro.addstrategy(
        HmaStateStrengthStrategy,
        fast=fast, mid1=mid1, mid2=mid2, mid3=mid3,
        atr_mult=atr_mult, printlog=False
    )
    strat = cerebro.run()[0]

    # Sharpe
    s = strat.analyzers.sharpe.get_analysis().get("sharperatio")
    sharpe = s if s is not None else float("-inf")

    # Expectancy
    tr = strat.analyzers.trades.get_analysis()
    won  = tr.get("won",{}).get("total", 0)
    lost = tr.get("lost",{}).get("total", 0)
    avg_w = tr.get("won",{}).get("pnl",{}).get("average", 0.0)
    avg_l = tr.get("lost",{}).get("pnl",{}).get("average", 0.0)
    total = won + lost
    if total:
        wr = won/total; lr = lost/total
        expectancy = wr*avg_w + lr*avg_l
    else:
        expectancy = float("-inf")

    return sharpe, expectancy, won, lost


if __name__ == "__main__":
    for SYMBOL in STOCKS:
        out_fname = f"{SYMBOL}_hma_opt.csv"
        print(f"\nWriting all results for {SYMBOL} into {out_fname}\n")

        with open(out_fname, "w", newline="") as fout:
            writer = csv.writer(fout)
            writer.writerow([
                "stage",
                "fast", "mid1", "mid2", "mid3",
                "sharpe", "expectancy", "won", "lost"
            ])

            # ── Stage-1 scan fast/mid1 ─────────────────────────────────────────
            stage1 = []
            for fast in FAST_RANGE:
                for mid1 in MID1_RANGE:
                    # default mid2/3 = fast×2, fast×4 for stage-1
                    s, e, won, lost = backtest(SYMBOL, fast, mid1, fast*2, fast*4, ATR_MULT)
                    stage1.append((fast, mid1, s, e))
                    writer.writerow([
                        "stage1",
                        fast, mid1, "", "",
                        f"{s:.6f}", f"{e:.6f}", won, lost
                    ])
                    print(f"[{SYMBOL}] Stage1 fast={fast}, mid1={mid1} → "
                          f"Sharpe={s: .3f}, Exp={e: .3f}, W/L={won}/{lost}")

            # pick top-N by chosen METRIC
            idx = 2 if METRIC == "sharpe" else 3
            top = sorted(stage1, key=lambda x: x[idx], reverse=True)[:TOP_N]
            print(f"\n[{SYMBOL}] Top {TOP_N} fast/mid1 by {METRIC}:")
            for f, m, sh, ex in top:
                print(f"  fast={f}, mid1={m} → Sharpe={sh:.3f}, Exp={ex:.3f}")

            # ── Stage-2 drill mid2/mid3 on those top‐pairs ─────────────────────
            print(f"\n[{SYMBOL}] Stage2 drill on mid2/mid3:\n")
            for fast, mid1, _, _ in top:
                for mid2 in MID2_RANGE:
                    for mid3 in MID3_RANGE:
                        # enforce ascending order
                        if not (fast < mid1 < mid2 < mid3):
                            continue
                        s2, e2, w2, l2 = backtest(SYMBOL, fast, mid1, mid2, mid3, ATR_MULT)
                        writer.writerow([
                            "stage2",
                            fast, mid1, mid2, mid3,
                            f"{s2:.6f}", f"{e2:.6f}", w2, l2
                        ])
                        print(f"  fast={fast}, mid1={mid1}, mid2={mid2}, mid3={mid3} → "
                              f"Sharpe={s2:.3f}, Exp={e2:.3f}, W/L={w2}/{l2}")

        print(f"\nDone → {out_fname}\n")
