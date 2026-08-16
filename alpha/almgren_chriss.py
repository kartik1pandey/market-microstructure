"""Almgren & Chriss (2000), "Optimal execution of portfolio transactions."

Minimizes a weighted combination of expected market-impact cost and the variance of that
cost, governed by a risk-aversion parameter. Higher risk aversion -> faster (more
front-loaded) liquidation, since spending longer in the market means more exposure to price
variance.
"""
from __future__ import annotations

import numpy as np


def kappa_ac(risk_aversion: float, sigma: float, eta: float) -> float:
    """The AC 'urgency' parameter - how strongly risk aversion accelerates liquidation.

    Named kappa_ac (not kappa) to avoid confusion with the Avellaneda-Stoikov order-arrival
    decay parameter kappa in avellaneda_stoikov.py, which measures something unrelated.
    """
    return float(np.sqrt(risk_aversion * sigma**2 / eta))


def optimal_trajectory(
    initial_position: float,
    total_time: float,
    n_steps: int,
    risk_aversion: float,
    sigma: float,
    eta: float,
) -> np.ndarray:
    """Holdings remaining at n_steps+1 evenly spaced points from t=0 to t=total_time."""
    times = np.linspace(0, total_time, n_steps + 1)
    k = kappa_ac(risk_aversion, sigma, eta)

    if np.isclose(k * total_time, 0):
        # risk-neutral limit: linear (TWAP) schedule
        return initial_position * (1 - times / total_time)

    return initial_position * np.sinh(k * (total_time - times)) / np.sinh(k * total_time)


def trade_schedule(trajectory: np.ndarray) -> np.ndarray:
    """Per-interval trade sizes (positive = shares sold) implied by a holdings trajectory."""
    return -np.diff(trajectory)
