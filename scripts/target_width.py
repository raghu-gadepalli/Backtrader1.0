import pandas as pd

df = pd.read_csv("supertrend_sweep_results.csv")
# filter for your window & period
sel = df[(df.window=="Jan-Jun") & (df.period==120)]
# pick the best multiplier
best = sel.loc[sel.sharpe.idxmax()]
vol = best.vol_baseline
m   = best.mult
target_width = vol * m
print(f"target_width = {vol:.4f}  {m:.2f} = {target_width:.4f}")
