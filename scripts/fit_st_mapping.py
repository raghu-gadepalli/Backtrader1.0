#!/usr/bin/env python3
import pandas as pd
import numpy as np

# 1. Load your full SuperTrend sweep (with vol_baseline)
df = pd.read_csv("supertrend_sweep_results.csv")

# 2. Restrict to your chosen period (e.g. period=240)
df240 = df[df["period"] == 240].copy()

# 3. Pick the best mult per window by Sharpe
best = (
    df240.loc[df240.groupby("window")["sharpe"].idxmax()]
         .loc[:, ["window", "vol_baseline", "mult"]]
         .rename(columns={"mult": "best_mult"})
)

print("Calibration points:")
print(best)

# 4. Fit best_mult  a + b * vol_baseline
a, b = np.polyfit(best["vol_baseline"], best["best_mult"], 1)
print(f"\nFitted mapping:\n  best_mult = {a:.4f} + {b:.4f}  vol_baseline")
