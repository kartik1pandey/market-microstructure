"""Calibrates Avellaneda-Stoikov / Almgren-Chriss parameters from captured tick data.

sigma: realized volatility of mid-price log returns, fixed-time resampled.
kappa/A: order-arrival intensity decay lambda(delta) = A * exp(-kappa*delta), fit from
trade distances relative to contemporaneous mid-price.
eta: temporary market-impact coefficient, price change per unit net signed volume.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calibrate_sigma(depth_df: pd.DataFrame, sample_interval: str = "1s") -> float:
    """Realized vol of mid-price log returns, resampled to a fixed time grid.

    depth_df needs columns: ts_ms, mid_price.
    Returns sigma per sample_interval unit (e.g. per second if sample_interval="1s").
    """
    series = pd.Series(
        depth_df["mid_price"].to_numpy(),
        index=pd.to_datetime(depth_df["ts_ms"], unit="ms", utc=True),
    ).sort_index()
    resampled = series.resample(sample_interval).last().ffill()
    log_returns = np.log(resampled / resampled.shift(1)).dropna()
    return float(log_returns.std())


def _trade_distance_from_mid(trades_df: pd.DataFrame, depth_df: pd.DataFrame) -> pd.DataFrame:
    """For each trade, find the most recent depth tick at/before its time and compute
    |trade_price - mid_price| at that moment."""
    trades = trades_df.sort_values("ts_ms").reset_index(drop=True)
    depth = depth_df.sort_values("ts_ms").reset_index(drop=True)
    trades["ts_ms"] = trades["ts_ms"].astype("float64")
    depth = depth.assign(ts_ms=depth["ts_ms"].astype("float64"))

    merged = pd.merge_asof(
        trades, depth[["ts_ms", "mid_price"]], on="ts_ms", direction="backward"
    )
    merged = merged.dropna(subset=["mid_price"])
    merged["distance"] = (merged["price"] - merged["mid_price"]).abs()
    return merged


def calibrate_kappa(
    trades_df: pd.DataFrame, depth_df: pd.DataFrame, n_bins: int = 5
) -> tuple[float, float]:
    """Fits lambda(delta) = A * exp(-kappa*delta) via quantile-binned trade distances.

    Quantile bins (rather than fixed-width) guarantee non-degenerate bins even when trade
    distances cluster tightly, e.g. in a very liquid, tight-spread market.
    Returns (A, kappa).
    """
    merged = _trade_distance_from_mid(trades_df, depth_df)
    merged = merged[merged["distance"] > 0]  # log(0) undefined; drop exact-mid prints

    time_span_seconds = (merged["ts_ms"].max() - merged["ts_ms"].min()) / 1000.0

    merged = merged.copy()
    merged["bin"] = pd.qcut(merged["distance"], q=n_bins, duplicates="drop")
    grouped = merged.groupby("bin", observed=True).agg(
        mean_distance=("distance", "mean"), count=("distance", "size")
    )
    grouped["rate"] = grouped["count"] / time_span_seconds

    x = grouped["mean_distance"].to_numpy()
    y = np.log(grouped["rate"].to_numpy())
    slope, intercept = np.polyfit(x, y, 1)

    kappa = -slope
    a_param = float(np.exp(intercept))
    return a_param, float(kappa)


def calibrate_eta(trades_df: pd.DataFrame, depth_df: pd.DataFrame, bucket: str = "1s") -> float:
    """Temporary market-impact coefficient: regression of mid-price change on net signed
    volume (buy volume - sell volume) over fixed time buckets.

    is_buyer_maker=True means the buyer was resting (maker), so the trade was seller-
    initiated - counted as negative (sell) volume. False means buyer-initiated (positive).
    """
    trades = trades_df.copy()
    trades["time"] = pd.to_datetime(trades["ts_ms"], unit="ms", utc=True)
    trades["signed_qty"] = np.where(trades["is_buyer_maker"], -trades["qty"], trades["qty"])
    net_volume = trades.set_index("time")["signed_qty"].resample(bucket).sum()

    depth = depth_df.copy()
    depth["time"] = pd.to_datetime(depth["ts_ms"], unit="ms", utc=True)
    mid = depth.set_index("time")["mid_price"].resample(bucket).last().ffill()
    price_change = mid.diff()

    panel = pd.DataFrame({"net_volume": net_volume, "price_change": price_change}).dropna()
    panel = panel[panel["net_volume"] != 0]

    slope, _ = np.polyfit(panel["net_volume"], panel["price_change"], 1)
    return float(slope)
