#!/usr/bin/env python3
# scripts/extract_top3.py

import os
import pandas as pd

# ─── CONFIG ────────────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_DIR = os.path.join(_ROOT, "results")

# Paths to your optimization CSVs
FILES = {
    "INFY": os.path.join(RESULTS_DIR, "hma_ratio_optimization_infy.csv"),
    "RELIANCE": os.path.join(RESULTS_DIR, "hma_ratio_optimization.csv"),
    "ICICIBANK": os.path.join(RESULTS_DIR, "hma_ratio_optimization_icici.csv"),
}

# Minimum trades threshold to consider a combo
MIN_TRADES = 20

# Manual cluster assignment (adjust as needed)
CLUSTER_MAP = {
    "INFY": 1,
    "RELIANCE": 2,
    "ICICIBANK": 1,
}


def main():
    # 1) Load and tag per-stock results
    dfs = []
    for symbol, path in FILES.items():
        df = pd.read_csv(path)
        df["symbol"] = symbol
        dfs.append(df)
    df_all = pd.concat(dfs, ignore_index=True)

    # 2) Top 3 per stock (filter by MIN_TRADES)
    top3_stock = (
        df_all[df_all["trades"] >= MIN_TRADES]
        .sort_values(["symbol", "sharpe"], ascending=[True, False])
        .groupby("symbol")
        .head(3)
        .reset_index(drop=True)
    )
    top3_stock.to_csv(os.path.join(RESULTS_DIR, "top3_per_stock.csv"), index=False)
    print("\nTop 3 HMA Crossovers per Stock saved to results/top3_per_stock.csv")
    print(top3_stock.to_string(index=False))

    # 3) Assign clusters and compute cluster‐average performance
    df_all["cluster"] = df_all["symbol"].map(CLUSTER_MAP)
    cluster_perf = (
        df_all
        .groupby(["cluster", "fast", "slow"], as_index=False)
        .agg(
            avg_sharpe=("sharpe", "mean"),
            avg_trades=("trades", "mean"),
            avg_winpct=("win%", "mean")
        )
    )

    # 4) Top 3 per cluster
    top3_cluster = (
        cluster_perf
        .sort_values(["cluster", "avg_sharpe"], ascending=[True, False])
        .groupby("cluster")
        .head(3)
        .reset_index(drop=True)
    )
    top3_cluster.to_csv(os.path.join(RESULTS_DIR, "top3_per_cluster.csv"), index=False)
    print("\nTop 3 HMA Crossovers per Cluster saved to results/top3_per_cluster.csv")
    print(top3_cluster.to_string(index=False))


if __name__ == "__main__":
    main()
