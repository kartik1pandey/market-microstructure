import numpy as np
import pandas as pd
import pytest

from alpha.backtest import (
    assert_no_overlap,
    compare_ac_vs_twap,
    execution_cost,
    naive_quote_fn,
    sharpe_like,
    simulate_market_making,
)


def test_assert_no_overlap_passes_for_disjoint_windows():
    calibration = pd.DataFrame({"ts_ms": [0, 1000, 2000]})
    evaluation = pd.DataFrame({"ts_ms": [3000, 4000, 5000]})
    assert_no_overlap(calibration, evaluation)  # should not raise


def test_assert_no_overlap_raises_for_overlapping_windows():
    calibration = pd.DataFrame({"ts_ms": [0, 1000, 5000]})
    evaluation = pd.DataFrame({"ts_ms": [3000, 4000, 6000]})
    with pytest.raises(AssertionError):
        assert_no_overlap(calibration, evaluation)


def test_simulate_market_making_buys_on_sell_initiated_trade_at_bid():
    depth_df = pd.DataFrame({"ts_ms": [0, 1000, 2000], "mid_price": [100.0, 100.0, 100.0]})
    # a sell-initiated trade (is_buyer_maker=True) at 99.5, at/below any reasonable fixed bid
    trades_df = pd.DataFrame(
        {"ts_ms": [500], "price": [99.0], "qty": [0.5], "is_buyer_maker": [True]}
    )

    result = simulate_market_making(depth_df, trades_df, naive_quote_fn(half_spread=0.5))

    assert result["inventory"].iloc[-1] == pytest.approx(0.5)
    assert result["cash"].iloc[-1] < 0  # spent cash to buy


def test_simulate_market_making_sells_on_buy_initiated_trade_at_ask():
    depth_df = pd.DataFrame({"ts_ms": [0, 1000, 2000], "mid_price": [100.0, 100.0, 100.0]})
    # a buy-initiated trade (is_buyer_maker=False) at 101, at/above any reasonable fixed ask
    trades_df = pd.DataFrame(
        {"ts_ms": [500], "price": [101.0], "qty": [0.3], "is_buyer_maker": [False]}
    )

    result = simulate_market_making(depth_df, trades_df, naive_quote_fn(half_spread=0.5))

    assert result["inventory"].iloc[-1] == pytest.approx(-0.3)
    assert result["cash"].iloc[-1] > 0  # received cash from selling


def test_sharpe_like_zero_when_pnl_constant():
    pnl = pd.Series([100.0, 100.0, 100.0, 100.0])
    assert sharpe_like(pnl) == 0.0


def test_sharpe_like_positive_for_noisy_but_increasing_pnl():
    # perfectly linear P&L has zero-variance returns (a degenerate edge case handled by
    # returning 0.0 to avoid divide-by-zero) - use slightly noisy increments instead so the
    # denominator is non-zero and the sign of the ratio is meaningful.
    pnl = pd.Series([100.0, 101.2, 102.0, 103.3, 104.1])
    assert sharpe_like(pnl) > 0


def test_execution_cost_matches_hand_calculation():
    price_path = np.array([10.0, 11.0])
    schedule = np.array([5.0, 5.0])
    result = execution_cost(price_path, schedule, arrival_price=9.0)

    assert result["proceeds"] == pytest.approx(5 * 10.0 + 5 * 11.0)
    assert result["avg_execution_price"] == pytest.approx((50.0 + 55.0) / 10.0)


def test_ac_beats_twap_when_price_is_declining():
    """If price falls steadily during liquidation, front-loading (AC with high risk
    aversion) should sell more early at better prices than a linear TWAP schedule."""
    n_steps = 50
    price_path = np.linspace(100.0, 90.0, n_steps + 1)  # steadily declining

    result = compare_ac_vs_twap(
        price_path, initial_position=1000, total_time=50, risk_aversion=5.0, sigma=0.01, eta=0.001
    )

    assert result["ac"]["avg_execution_price"] > result["twap"]["avg_execution_price"]
