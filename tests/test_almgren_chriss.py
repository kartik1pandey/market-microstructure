import numpy as np
import pytest

from alpha.almgren_chriss import optimal_trajectory, trade_schedule


def test_trajectory_starts_at_initial_position_and_ends_at_zero():
    trajectory = optimal_trajectory(
        initial_position=1000, total_time=10, n_steps=10, risk_aversion=1e-6, sigma=0.01, eta=0.001
    )
    assert trajectory[0] == pytest.approx(1000)
    assert trajectory[-1] == pytest.approx(0, abs=1e-6)


def test_zero_risk_aversion_gives_linear_twap_schedule():
    trajectory = optimal_trajectory(
        initial_position=1000, total_time=10, n_steps=10, risk_aversion=0.0, sigma=0.01, eta=0.001
    )
    expected = 1000 * (1 - np.linspace(0, 10, 11) / 10)
    np.testing.assert_allclose(trajectory, expected, atol=1e-8)


def test_higher_risk_aversion_front_loads_the_trajectory():
    """The checklist's own criterion: higher lambda -> less inventory remaining at t=T/2."""
    low_aversion = optimal_trajectory(
        initial_position=1000, total_time=10, n_steps=100, risk_aversion=0.001, sigma=0.01, eta=0.001
    )
    high_aversion = optimal_trajectory(
        initial_position=1000, total_time=10, n_steps=100, risk_aversion=1.0, sigma=0.01, eta=0.001
    )

    midpoint = 50  # t = T/2 at n_steps=100
    assert high_aversion[midpoint] < low_aversion[midpoint]


def test_trade_schedule_sums_to_initial_position():
    trajectory = optimal_trajectory(
        initial_position=1000, total_time=10, n_steps=20, risk_aversion=0.1, sigma=0.01, eta=0.001
    )
    schedule = trade_schedule(trajectory)
    assert schedule.sum() == pytest.approx(1000)
    assert (schedule >= 0).all()  # monotonically liquidating, never buying back
