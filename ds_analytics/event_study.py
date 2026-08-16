"""Synthetic-control event study.

Estimand: did ending the TUSD zero-maker-fee promotion (2024-07-16 00:00 UTC) measurably
widen BTC/TUSD liquidity relative to a synthetic control built from unaffected BTC pairs?

Outcome metric is a liquidity proxy - (high-low)/close per bar - since true historical
bid-ask spread isn't available (see docs/build-notes.md for why).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def liquidity_proxy(df: pd.DataFrame) -> pd.Series:
    """(high-low)/close per row - a standard spread/liquidity proxy without L2 history."""
    return (df["high"] - df["low"]) / df["close"]


def build_panel(klines_by_symbol: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Wide panel: one row per open_time, one column per symbol's liquidity proxy."""
    series = {}
    for symbol, df in klines_by_symbol.items():
        indexed = df.set_index("open_time")
        series[symbol] = liquidity_proxy(indexed)
    panel = pd.DataFrame(series).sort_index()
    return panel.dropna()


def pre_period_correlation(
    panel: pd.DataFrame, treated: str, donors: list[str], event_time
) -> pd.Series:
    pre = panel[panel.index < event_time]
    return pre[donors].corrwith(pre[treated])


def fit_synthetic_control(
    panel: pd.DataFrame, treated: str, donors: list[str], event_time
) -> tuple[pd.Series, float]:
    """Non-negative weights summing to 1, minimizing pre-period RMSE against the treated unit."""
    pre = panel[panel.index < event_time]
    y = pre[treated].to_numpy()
    x = pre[donors].to_numpy()

    def objective(w):
        return np.sqrt(np.mean((y - x @ w) ** 2))

    n = len(donors)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0, 1)] * n
    result = minimize(objective, x0=np.full(n, 1 / n), bounds=bounds, constraints=constraints)

    weights = pd.Series(result.x, index=donors)
    return weights, result.fun


def estimate_effect(
    panel: pd.DataFrame, treated: str, weights: pd.Series, event_time, post_end
) -> dict:
    post = panel[(panel.index >= event_time) & (panel.index <= post_end)]
    synthetic = post[weights.index].to_numpy() @ weights.to_numpy()
    actual = post[treated].to_numpy()
    gap = actual - synthetic
    return {
        "mean_actual": float(actual.mean()),
        "mean_synthetic": float(synthetic.mean()),
        "mean_gap": float(gap.mean()),
        "pct_effect": float(gap.mean() / synthetic.mean() * 100),
    }


def placebo_test(
    panel: pd.DataFrame, treated: str, donors: list[str], event_time, post_end
) -> dict[str, float]:
    """Re-run the identical method with each donor as the 'treated' unit instead."""
    results = {}
    for placebo_unit in donors:
        placebo_donors = [u for u in [treated, *donors] if u != placebo_unit]
        weights, _ = fit_synthetic_control(panel, placebo_unit, placebo_donors, event_time)
        effect = estimate_effect(panel, placebo_unit, weights, event_time, post_end)
        results[placebo_unit] = effect["mean_gap"]
    return results
