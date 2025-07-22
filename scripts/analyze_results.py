#!/usr/bin/env python3
# analyze_results.py  (paths hard-coded)

import os
from pathlib import Path
import pandas as pd
import numpy as np
import argparse

# ─── EDIT THESE IF YOUR FOLDERS DIFFER ─────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]            # C:\projects\backtrader
RESULTS_DIR  = PROJECT_ROOT / "results"
SUMMARY_CSV  = RESULTS_DIR / "supertrend_test_results.csv"
TRADES_CSV   = RESULTS_DIR / "supertrend_trade_results.csv"
OUT_DIR      = RESULTS_DIR / "analysis"
# ───────────────────────────────────────────────────────────────────

def bin_volatility(df_trades: pd.DataFrame) -> pd.DataFrame:
    """Add vol_bin column using atr_pct terciles."""
    q = df_trades["atr_pct"].quantile([0.33, 0.66]).values
    bins   = [-np.inf, q[0], q[1], np.inf]
    labels = ["LOW", "MID", "HIGH"]
    return df_trades.assign(vol_bin=pd.cut(df_trades["atr_pct"], bins=bins, labels=labels))

def main(plot: bool):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Load ----
    if not SUMMARY_CSV.exists():
        raise FileNotFoundError(f"Summary CSV not found: {SUMMARY_CSV}")
    if not TRADES_CSV.exists():
        raise FileNotFoundError(f"Trades CSV not found:  {TRADES_CSV}")

    sum_df = pd.read_csv(SUMMARY_CSV)
    tr_df  = pd.read_csv(TRADES_CSV, parse_dates=["dt_in","dt_out"], infer_datetime_format=True)

    sum_df.columns = [c.lower().strip() for c in sum_df.columns]
    tr_df.columns  = [c.lower().strip() for c in tr_df.columns]

    # 1) Monthly ranking
    ranked = sum_df.sort_values(["period_label","sharpe","expectancy"], ascending=[True, False, False])
    ranked.to_csv(OUT_DIR / "ranked_by_month.csv", index=False)

    # 2) Stability across months
    stability = (sum_df.groupby(["period","mult"], as_index=False)
                 .agg(mean_sharpe=("sharpe","mean"),
                      std_sharpe=("sharpe","std"),
                      mean_exp=("expectancy","mean"),
                      trades_total=("trades","sum")))
    stability = stability.sort_values("mean_sharpe", ascending=False)
    stability.to_csv(OUT_DIR / "stability_across_months.csv", index=False)

    # 3) Volatility bins (if atr_pct exists)
    vol_tables_written = False
    if "atr_pct" in tr_df.columns:
        tr_df = tr_df.dropna(subset=["atr_pct"])
        if len(tr_df):
            tr_df = bin_volatility(tr_df)

            vol_summary = (tr_df.groupby("vol_bin")
                           .agg(trades=("pnl","count"),
                                win_rate=("pnl", lambda x: (x>0).mean()*100),
                                expectancy=("pnl","mean"),
                                avg_win=("pnl", lambda x: x[x>0].mean() if (x>0).any() else 0),
                                avg_loss=("pnl", lambda x: x[x<=0].mean() if (x<=0).any() else 0))
                           .reset_index())
            vol_summary.to_csv(OUT_DIR / "vol_bin_summary.csv", index=False)

            vol_cfg = (tr_df.groupby(["period","mult","vol_bin"], as_index=False)
                       .agg(trades=("pnl","count"),
                            exp=("pnl","mean"),
                            win_rate=("pnl", lambda x: (x>0).mean()*100)))
            vol_cfg.to_csv(OUT_DIR / "vol_bin_per_config.csv", index=False)

            pivot_exp = vol_cfg.pivot_table(index=["period","mult"], columns="vol_bin",
                                            values="exp", aggfunc="mean")
            good_all = pivot_exp.dropna().loc[(pivot_exp > 0).all(axis=1)].reset_index()
            good_all.to_csv(OUT_DIR / "configs_positive_all_bins.csv", index=False)

            vol_tables_written = True

    # 4) Markdown report
    with (OUT_DIR / "report.md").open("w") as f:
        f.write("# SuperTrend Analysis Report\n\n")
        f.write("## 1. Monthly Ranking (Sharpe desc)\n")
        f.write("See `ranked_by_month.csv`.\n\n")
        f.write("## 2. Stability Across Months\n")
        f.write("See `stability_across_months.csv`.\n\n")
        if vol_tables_written:
            f.write("## 3. Volatility Bin Results\n")
            f.write("- `vol_bin_summary.csv`\n")
            f.write("- `vol_bin_per_config.csv`\n")
            f.write("- `configs_positive_all_bins.csv`\n\n")
        else:
            f.write("## 3. Volatility Bin Results\n`atr_pct` not found or empty — skipped.\n\n")

    # 5) Optional plots
    if plot:
        try:
            import matplotlib.pyplot as plt
            # Mean Sharpe vs Mult
            fig = plt.figure()
            tmp = stability.sort_values("mult")
            plt.plot(tmp["mult"], tmp["mean_sharpe"], marker="o")
            plt.title("Mean Sharpe vs Multiplier")
            plt.xlabel("Multiplier")
            plt.ylabel("Mean Sharpe")
            fig.savefig(OUT_DIR / "mean_sharpe_vs_mult.png", dpi=120, bbox_inches="tight")
            plt.close(fig)
        except Exception as e:
            print("Plotting failed:", e)

    print(f"Done. Outputs in: {OUT_DIR}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plot", action="store_true", help="generate a simple plot image")
    args = parser.parse_args()
    main(args.plot)
