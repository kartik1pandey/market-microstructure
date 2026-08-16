"""Reproduces the backtest report in backtest_report.md end to end.

Usage: python -m alpha.run_backtest
"""
from __future__ import annotations

import glob
import json

import numpy as np
import pandas as pd

from alpha.almgren_chriss import optimal_trajectory
from alpha.avellaneda_stoikov import compute_quotes
from alpha.backtest import (
    as_quote_fn,
    assert_no_overlap,
    compare_ac_vs_twap,
    naive_quote_fn,
    sharpe_like,
    simulate_market_making,
)
from alpha.calibration import calibrate_eta, calibrate_kappa, calibrate_sigma

CALIBRATION_FRACTION = 0.70
GAMMA = 300
RISK_AVERSION = 50000
LIQUIDATION_SIZE = 5.0


def load_lake() -> tuple[pd.DataFrame, pd.DataFrame]:
    depth_files = glob.glob("data/lake/depth_ticks/**/*.parquet", recursive=True)
    trade_files = glob.glob("data/lake/trades/**/*.parquet", recursive=True)
    depth = (
        pd.concat([pd.read_parquet(f) for f in depth_files], ignore_index=True)
        .sort_values("ts_ms")
        .reset_index(drop=True)
    )
    trades = (
        pd.concat([pd.read_parquet(f) for f in trade_files], ignore_index=True)
        .sort_values("ts_ms")
        .reset_index(drop=True)
    )
    depth["mid_price"] = (depth["best_bid"] + depth["best_ask"]) / 2.0
    return depth, trades


def main() -> None:
    depth, trades = load_lake()
    print(f"Full data span: {pd.to_datetime(depth['ts_ms'].min(), unit='ms')} to "
          f"{pd.to_datetime(depth['ts_ms'].max(), unit='ms')}")

    cutoff = depth["ts_ms"].quantile(CALIBRATION_FRACTION)
    calib_depth = depth[depth["ts_ms"] < cutoff].reset_index(drop=True)
    calib_trades = trades[trades["ts_ms"] < cutoff].reset_index(drop=True)
    eval_depth = depth[depth["ts_ms"] >= cutoff].reset_index(drop=True)
    eval_trades = trades[trades["ts_ms"] >= cutoff].reset_index(drop=True)
    assert_no_overlap(calib_depth, eval_depth)

    print(f"\nCalibration window: {pd.to_datetime(calib_depth['ts_ms'].min(), unit='ms')} to "
          f"{pd.to_datetime(calib_depth['ts_ms'].max(), unit='ms')} "
          f"({len(calib_depth)} depth, {len(calib_trades)} trades)")
    print(f"Evaluation window:  {pd.to_datetime(eval_depth['ts_ms'].min(), unit='ms')} to "
          f"{pd.to_datetime(eval_depth['ts_ms'].max(), unit='ms')} "
          f"({len(eval_depth)} depth, {len(eval_trades)} trades)")

    # Refit-stability check: two non-overlapping halves of the calibration window
    calib_midpoint = calib_depth["ts_ms"].quantile(0.5)
    w1_depth = calib_depth[calib_depth["ts_ms"] < calib_midpoint]
    w1_trades = calib_trades[calib_trades["ts_ms"] < calib_midpoint]
    w2_depth = calib_depth[calib_depth["ts_ms"] >= calib_midpoint]
    w2_trades = calib_trades[calib_trades["ts_ms"] >= calib_midpoint]

    print("\n--- Refit stability (two non-overlapping calibration sub-windows) ---")
    print(f"sigma: {calibrate_sigma(w1_depth):.3e} vs {calibrate_sigma(w2_depth):.3e}")
    a1, k1 = calibrate_kappa(w1_trades, w1_depth, n_bins=5)
    a2, k2 = calibrate_kappa(w2_trades, w2_depth, n_bins=5)
    print(f"kappa: {k1:.4f} vs {k2:.4f}  (A: {a1:.4f} vs {a2:.4f})")
    print(f"eta: {calibrate_eta(w1_trades, w1_depth):.4f} vs {calibrate_eta(w2_trades, w2_depth):.4f}")

    # Full calibration-window estimates - what the backtest actually uses
    sigma = calibrate_sigma(calib_depth)
    a_param, kappa = calibrate_kappa(calib_trades, calib_depth, n_bins=5)
    eta = calibrate_eta(calib_trades, calib_depth)
    avg_half_spread = (calib_depth["best_ask"] - calib_depth["best_bid"]).mean() / 2.0
    print(f"\nFull calibration-window estimates: sigma={sigma}, A={a_param}, kappa={kappa}, "
          f"eta={eta}, avg_half_spread={avg_half_spread}")

    # AS vs naive fixed-spread market-making
    as_fn = as_quote_fn(gamma=GAMMA, sigma=sigma, kappa=kappa)
    naive_fn = naive_quote_fn(half_spread=avg_half_spread)
    as_result = simulate_market_making(eval_depth, eval_trades, as_fn)
    naive_result = simulate_market_making(eval_depth, eval_trades, naive_fn)

    print(f"\n--- AS (gamma={GAMMA}) vs naive fixed-spread ---")
    print(f"AS:    pnl={as_result['pnl'].iloc[-1]:.4f}, "
          f"final_inv={as_result['inventory'].iloc[-1]:.4f}, "
          f"max_inv={as_result['inventory'].abs().max():.4f}, "
          f"sharpe={sharpe_like(as_result['pnl']):.6f}, "
          f"fills={(as_result['inventory'].diff() != 0).sum()}")
    print(f"Naive: pnl={naive_result['pnl'].iloc[-1]:.4f}, "
          f"final_inv={naive_result['inventory'].iloc[-1]:.4f}, "
          f"max_inv={naive_result['inventory'].abs().max():.4f}, "
          f"sharpe={sharpe_like(naive_result['pnl']):.6f}, "
          f"fills={(naive_result['inventory'].diff() != 0).sum()}")

    # AC vs TWAP execution-cost comparison
    price_path = (
        eval_depth.set_index(pd.to_datetime(eval_depth["ts_ms"], unit="ms", utc=True))["mid_price"]
        .resample("10s")
        .last()
        .ffill()
        .to_numpy()
    )
    n_steps = len(price_path) - 1
    sigma_10s = sigma * np.sqrt(10)

    ac_result = compare_ac_vs_twap(
        price_path,
        initial_position=LIQUIDATION_SIZE,
        total_time=float(n_steps),
        risk_aversion=RISK_AVERSION,
        sigma=sigma_10s,
        eta=eta,
    )
    ac_traj = optimal_trajectory(LIQUIDATION_SIZE, float(n_steps), n_steps, RISK_AVERSION, sigma_10s, eta)
    twap_traj = optimal_trajectory(LIQUIDATION_SIZE, float(n_steps), n_steps, 0.0, sigma_10s, eta)

    print(f"\n--- AC (risk_aversion={RISK_AVERSION}) vs TWAP, liquidate {LIQUIDATION_SIZE} BTC "
          f"over {n_steps} x 10s steps, price {price_path[0]:.2f} -> {price_path[-1]:.2f} ---")
    print(f"AC remaining at T/2: {ac_traj[n_steps // 2]:.4f} (TWAP: {twap_traj[n_steps // 2]:.4f})")
    print(json.dumps(ac_result, indent=2))


if __name__ == "__main__":
    main()
