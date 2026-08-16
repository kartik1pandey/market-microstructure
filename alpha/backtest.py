"""Walk-forward backtest: Avellaneda-Stoikov market-making vs a naive fixed-spread baseline,
and Almgren-Chriss optimal execution vs naive TWAP - both evaluated against real captured
tick data, never against the same window used for calibration.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from alpha.almgren_chriss import optimal_trajectory, trade_schedule
from alpha.avellaneda_stoikov import compute_quotes

MAX_FILL_QTY = 1.0  # caps per-bucket fill size so one huge print can't dominate a fill


def assert_no_overlap(calibration_df: pd.DataFrame, evaluation_df: pd.DataFrame) -> None:
    """Explicit check that the calibration window and evaluation window never overlap."""
    calib_end = calibration_df["ts_ms"].max()
    eval_start = evaluation_df["ts_ms"].min()
    assert calib_end <= eval_start, (
        f"Calibration window (ends {calib_end}) overlaps evaluation window (starts {eval_start})"
    )


def as_quote_fn(gamma: float, sigma: float, kappa: float):
    def fn(mid_price, inventory, time_remaining):
        q = compute_quotes(mid_price, inventory, gamma, sigma, time_remaining, kappa)
        return q.bid, q.ask

    return fn


def naive_quote_fn(half_spread: float):
    def fn(mid_price, inventory, time_remaining):
        return mid_price - half_spread, mid_price + half_spread

    return fn


def simulate_market_making(
    depth_df: pd.DataFrame, trades_df: pd.DataFrame, quote_fn, bucket: str = "1s"
) -> pd.DataFrame:
    """quote_fn(mid_price, inventory, time_remaining_fraction) -> (bid, ask).

    Fill assumption (a documented simplification, not realistic queue-priority execution):
    within each time bucket, a sell-initiated trade at/below our bid fills our bid (we buy);
    a buy-initiated trade at/above our ask fills our ask (we sell).
    """
    depth = depth_df.copy()
    depth["time"] = pd.to_datetime(depth["ts_ms"], unit="ms", utc=True)
    mid = depth.set_index("time")["mid_price"].resample(bucket).last().ffill()

    trades = trades_df.copy()
    trades["time"] = pd.to_datetime(trades["ts_ms"], unit="ms", utc=True)
    trades = trades.set_index("time")

    session_start = mid.index[0]
    session_end = mid.index[-1]
    total_seconds = max((session_end - session_start).total_seconds(), 1e-6)
    bucket_delta = pd.Timedelta(bucket)

    inventory = 0.0
    cash = 0.0
    rows = []

    for t, mid_price in mid.items():
        time_remaining = max((session_end - t).total_seconds(), 1e-6) / total_seconds
        bid, ask = quote_fn(mid_price, inventory, time_remaining)

        window = trades.loc[(trades.index >= t) & (trades.index < t + bucket_delta)]

        sells = window[window["is_buyer_maker"] & (window["price"] <= bid)]
        if not sells.empty:
            fill_qty = min(float(sells["qty"].sum()), MAX_FILL_QTY)
            inventory += fill_qty
            cash -= fill_qty * bid

        buys = window[(~window["is_buyer_maker"]) & (window["price"] >= ask)]
        if not buys.empty:
            fill_qty = min(float(buys["qty"].sum()), MAX_FILL_QTY)
            inventory -= fill_qty
            cash += fill_qty * ask

        rows.append(
            {
                "time": t,
                "mid_price": mid_price,
                "bid": bid,
                "ask": ask,
                "inventory": inventory,
                "cash": cash,
                "pnl": cash + inventory * mid_price,
            }
        )

    return pd.DataFrame(rows)


def sharpe_like(pnl_series: pd.Series) -> float:
    """Mean/stddev of period-over-period P&L changes - a simple risk-adjusted-return proxy."""
    returns = pnl_series.diff().dropna()
    if returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std())


def execution_cost(price_path: np.ndarray, schedule: np.ndarray, arrival_price: float) -> dict:
    """schedule: shares sold per interval. Returns proceeds and implementation shortfall
    relative to the arrival price (the price when the liquidation decision was made)."""
    proceeds = float(np.sum(schedule * price_path))
    total_shares = float(schedule.sum())
    avg_execution_price = proceeds / total_shares if total_shares else 0.0
    shortfall = (arrival_price - avg_execution_price) * total_shares
    return {
        "proceeds": proceeds,
        "avg_execution_price": avg_execution_price,
        "implementation_shortfall": shortfall,
    }


def compare_ac_vs_twap(
    price_path: np.ndarray,
    initial_position: float,
    total_time: float,
    risk_aversion: float,
    sigma: float,
    eta: float,
) -> dict:
    """price_path must have length n_steps+1, aligned with the trajectory's time grid."""
    n_steps = len(price_path) - 1

    ac_trajectory = optimal_trajectory(initial_position, total_time, n_steps, risk_aversion, sigma, eta)
    ac_schedule = trade_schedule(ac_trajectory)

    twap_trajectory = optimal_trajectory(initial_position, total_time, n_steps, 0.0, sigma, eta)
    twap_schedule = trade_schedule(twap_trajectory)

    arrival_price = price_path[0]
    return {
        "ac": execution_cost(price_path[1:], ac_schedule, arrival_price),
        "twap": execution_cost(price_path[1:], twap_schedule, arrival_price),
    }
