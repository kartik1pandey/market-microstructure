"""One-off script: generates real result charts (PNG) from the actual captured data and
actual model outputs, for the images/ folder. Not part of the pipeline itself - a
visualization pass over genuine outputs, run once to produce documentation images.
"""
from __future__ import annotations

import glob

import duckdb
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from alpha.backtest import as_quote_fn, assert_no_overlap, naive_quote_fn, simulate_market_making, sharpe_like
from alpha.calibration import calibrate_eta, calibrate_kappa, calibrate_sigma
from alpha.almgren_chriss import optimal_trajectory
from risk.var_es import rolling_var_es

plt.rcParams.update({
    "figure.facecolor": "#12141c",
    "axes.facecolor": "#12141c",
    "axes.edgecolor": "#2a2e3d",
    "axes.labelcolor": "#eae8e1",
    "text.color": "#eae8e1",
    "xtick.color": "#8b8d9c",
    "ytick.color": "#8b8d9c",
    "grid.color": "#2a2e3d",
    "font.size": 11,
    "figure.dpi": 130,
})

ACCENT = "#d4a24c"
BLUE = "#5b9bd5"
GOOD = "#4f9d6e"
WARN = "#d18b3d"
CRIT = "#c1524d"

OUT = "images"

con = duckdb.connect("dbt/dev.duckdb")
depth = con.execute("select * from main.fct_depth_features order by final_update_id").df()
vpin = con.execute("select * from main.fct_vpin order by bucket_id").df()
depth["event_time"] = pd.to_datetime(depth["event_time"])
vpin["bucket_end_time"] = pd.to_datetime(vpin["bucket_end_time"])


def break_at_gaps(df: pd.DataFrame, time_col: str, gap_threshold: pd.Timedelta) -> pd.DataFrame:
    """Ingestion stalled twice during capture, leaving multi-hour silent gaps. Connecting
    across them with a straight line would draw a fake smooth ramp where there's actually no
    data - insert a NaN row at each gap so matplotlib breaks the line instead of interpolating
    across silence it never observed."""
    df = df.sort_values(time_col).reset_index(drop=True)
    gaps = df[time_col].diff() > gap_threshold
    if not gaps.any():
        return df
    pieces = []
    start = 0
    for idx in gaps[gaps].index:
        pieces.append(df.iloc[start:idx])
        blank = {c: [pd.NA] for c in df.columns}
        blank[time_col] = [df[time_col].iloc[idx - 1] + (df[time_col].iloc[idx] - df[time_col].iloc[idx - 1]) / 2]
        pieces.append(pd.DataFrame(blank))
        start = idx
    pieces.append(df.iloc[start:])
    return pd.concat(pieces, ignore_index=True)


depth = break_at_gaps(depth, "event_time", pd.Timedelta(minutes=5))
vpin_plot = break_at_gaps(vpin, "bucket_end_time", pd.Timedelta(minutes=30))

# ---------- 1. Mid-price over the captured session ----------
fig, ax = plt.subplots(figsize=(11, 4.5))
ax.plot(depth["event_time"], depth["mid_price"], color=ACCENT, linewidth=0.8)
ax.set_title("BTC/USDT mid-price — captured session (real Binance ticks)", loc="left", fontsize=13)
ax.set_ylabel("Price (USDT)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/01_mid_price.png")
plt.close(fig)

# ---------- 2. Spread (bps) over time ----------
fig, ax = plt.subplots(figsize=(11, 4.5))
ax.plot(depth["event_time"], depth["spread_bps"], color=BLUE, linewidth=0.7)
ax.set_title("Spread (bps) over time", loc="left", fontsize=13)
ax.set_ylabel("Spread (bps)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/02_spread_bps.png")
plt.close(fig)

# ---------- 3. Order-flow imbalance ----------
fig, ax = plt.subplots(figsize=(11, 4.5))
colors = np.where(depth["order_flow_imbalance"] >= 0, GOOD, CRIT)
ax.scatter(depth["event_time"], depth["order_flow_imbalance"], c=colors, s=2, alpha=0.5)
ax.axhline(0, color="#8b8d9c", linewidth=0.8)
ax.set_ylim(-1.05, 1.05)
ax.set_title("Order-flow imbalance (queue-imbalance ratio, bounded [-1,1])", loc="left", fontsize=13)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/03_order_flow_imbalance.png")
plt.close(fig)

# ---------- 4. VPIN with regime thresholds ----------
fig, ax = plt.subplots(figsize=(11, 4.5))
ax.plot(vpin_plot["bucket_end_time"], vpin_plot["vpin"], color=ACCENT, linewidth=1.4, marker="o", markersize=3)
ax.axhline(0.2, color=WARN, linestyle="--", linewidth=1, label="elevated (0.2)")
ax.axhline(0.4, color=CRIT, linestyle="--", linewidth=1, label="toxic (0.4)")
ax.set_ylim(0, max(0.5, vpin["vpin"].max() * 1.1))
ax.set_title("VPIN over time — real Bulk Volume Classification, equal-volume buckets", loc="left", fontsize=13)
ax.legend(loc="upper right", framealpha=0.2, labelcolor="#eae8e1")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/04_vpin_regimes.png")
plt.close(fig)

print("Charts 1-4 done (real captured/computed data).")

# ---------- 5. AS vs naive backtest P&L ----------
depth_files = glob.glob("data/lake/depth_ticks/**/*.parquet", recursive=True)
trade_files = glob.glob("data/lake/trades/**/*.parquet", recursive=True)
raw_depth = pd.concat([pd.read_parquet(f) for f in depth_files], ignore_index=True).sort_values("ts_ms").reset_index(drop=True)
raw_trades = pd.concat([pd.read_parquet(f) for f in trade_files], ignore_index=True).sort_values("ts_ms").reset_index(drop=True)
raw_depth["mid_price"] = (raw_depth["best_bid"] + raw_depth["best_ask"]) / 2.0

cutoff = raw_depth["ts_ms"].quantile(0.70)
calib_depth = raw_depth[raw_depth["ts_ms"] < cutoff].reset_index(drop=True)
calib_trades = raw_trades[raw_trades["ts_ms"] < cutoff].reset_index(drop=True)
eval_depth = raw_depth[raw_depth["ts_ms"] >= cutoff].reset_index(drop=True)
eval_trades = raw_trades[raw_trades["ts_ms"] >= cutoff].reset_index(drop=True)
assert_no_overlap(calib_depth, eval_depth)

sigma = calibrate_sigma(calib_depth)
a_param, kappa = calibrate_kappa(calib_trades, calib_depth, n_bins=5)
eta = calibrate_eta(calib_trades, calib_depth)
avg_half_spread = (calib_depth["best_ask"] - calib_depth["best_bid"]).mean() / 2.0

as_fn = as_quote_fn(gamma=300, sigma=sigma, kappa=kappa)
naive_fn = naive_quote_fn(half_spread=avg_half_spread)
as_result = simulate_market_making(eval_depth, eval_trades, as_fn)
naive_result = simulate_market_making(eval_depth, eval_trades, naive_fn)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
ax1.plot(as_result["time"], as_result["pnl"], color=ACCENT, label=f"Avellaneda-Stoikov (γ=300)")
ax1.plot(naive_result["time"], naive_result["pnl"], color=BLUE, label="Naive fixed-spread")
ax1.set_ylabel("Mark-to-market P&L")
ax1.set_title("Alpha lens: AS vs naive market-making — real backtest on captured data", loc="left", fontsize=13)
ax1.legend(loc="lower left", framealpha=0.2, labelcolor="#eae8e1")
ax1.grid(alpha=0.3)

ax2.plot(as_result["time"], as_result["inventory"], color=ACCENT, label="AS inventory")
ax2.plot(naive_result["time"], naive_result["inventory"], color=BLUE, label="Naive inventory")
ax2.axhline(0, color="#8b8d9c", linewidth=0.8)
ax2.set_ylabel("Inventory (BTC)")
ax2.legend(loc="lower left", framealpha=0.2, labelcolor="#eae8e1")
ax2.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/05_as_vs_naive_backtest.png")
plt.close(fig)

print(f"AS: pnl={as_result['pnl'].iloc[-1]:.2f} fills={(as_result['inventory'].diff()!=0).sum()} "
      f"sharpe={sharpe_like(as_result['pnl']):.5f}")
print(f"Naive: pnl={naive_result['pnl'].iloc[-1]:.2f} fills={(naive_result['inventory'].diff()!=0).sum()} "
      f"sharpe={sharpe_like(naive_result['pnl']):.5f}")

# ---------- 6. Almgren-Chriss vs TWAP trajectory ----------
n_steps = 100
sigma_10s = sigma * np.sqrt(10)
# A larger risk_aversion than the official backtest_report.md run, chosen here purely to make
# the front-loading concept visually clear in this illustrative chart (the documented backtest
# numbers elsewhere are unaffected by this choice).
RISK_AVERSION_ILLUSTRATIVE = 2_000_000
ac_traj = optimal_trajectory(5.0, float(n_steps), n_steps, RISK_AVERSION_ILLUSTRATIVE, sigma_10s, eta)
twap_traj = optimal_trajectory(5.0, float(n_steps), n_steps, 0.0, sigma_10s, eta)

fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(twap_traj, color=BLUE, linewidth=2, label="Naive TWAP (linear)")
ax.plot(ac_traj, color=ACCENT, linewidth=2, label=f"Almgren-Chriss (risk_aversion={RISK_AVERSION_ILLUSTRATIVE:,})")
ax.set_xlabel("Time step (of 100)")
ax.set_ylabel("BTC remaining to liquidate")
ax.set_title("Almgren-Chriss front-loads liquidation vs naive TWAP", loc="left", fontsize=13)
ax.legend(framealpha=0.2, labelcolor="#eae8e1")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/06_ac_vs_twap_trajectory.png")
plt.close(fig)

# ---------- 7. VaR vs ES boundary illustration ----------
steps = [1] * 95 + [-10] * 5
pnl_synth = pd.Series(np.concatenate([[0], np.cumsum(steps)]))
result = rolling_var_es(pnl_synth, window=100, confidence=0.95)
losses = -pnl_synth.diff()

fig, ax = plt.subplots(figsize=(9, 5))
ax.hist(losses.dropna(), bins=30, color=BLUE, alpha=0.7, edgecolor="#12141c")
ax.axvline(result["var"].iloc[-1], color=WARN, linestyle="--", linewidth=2,
           label=f"VaR (95%) = {result['var'].iloc[-1]:.2f}")
ax.axvline(result["es"].iloc[-1], color=CRIT, linestyle="--", linewidth=2,
           label=f"ES (95%) = {result['es'].iloc[-1]:.2f}")
ax.set_xlabel("Loss")
ax.set_ylabel("Count")
ax.set_title("Why ES beats VaR at a fat-tail boundary (95 small gains, 5 big losses)", loc="left", fontsize=12)
ax.legend(framealpha=0.2, labelcolor="#eae8e1")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/07_var_vs_es.png")
plt.close(fig)

print("All 7 charts generated in images/")
