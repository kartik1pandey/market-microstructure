import numpy as np
import pandas as pd
import pytest

from ds_analytics.event_study import (
    build_panel,
    estimate_effect,
    fit_synthetic_control,
    liquidity_proxy,
    pre_period_correlation,
)


def test_liquidity_proxy_computes_high_low_over_close():
    df = pd.DataFrame({"high": [110.0], "low": [90.0], "close": [100.0]})
    result = liquidity_proxy(df)
    assert result.iloc[0] == 0.2  # (110-90)/100


def make_synthetic_panel(n=200, seed=0):
    """treated = 0.6*donor_a + 0.4*donor_b exactly in the pre-period, with a real gap
    injected in the post-period so the effect estimate has known ground truth.

    donor_a/donor_b share a common latent factor (like correlated assets sharing market-wide
    moves) plus small idiosyncratic noise, so each is individually highly correlated with
    treated - donor_c is pure independent noise, uncorrelated with anything."""
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-06-01", periods=n, freq="h", tz="UTC")
    event_time = index[150]

    common_factor = rng.standard_normal(n)
    donor_a = pd.Series(0.01 + 0.002 * common_factor + 0.001 * rng.standard_normal(n), index=index)
    donor_b = pd.Series(0.012 + 0.002 * common_factor + 0.001 * rng.standard_normal(n), index=index)
    donor_c = pd.Series(0.008 + 0.002 * rng.standard_normal(n), index=index)  # unrelated donor

    treated = 0.6 * donor_a + 0.4 * donor_b
    post_mask = index >= event_time
    treated = treated.copy()
    treated[post_mask] = treated[post_mask] + 0.01  # injected post-period gap

    panel = pd.DataFrame(
        {"TREATED": treated, "DONOR_A": donor_a, "DONOR_B": donor_b, "DONOR_C": donor_c}
    )
    return panel, event_time, index[-1]


def test_fit_synthetic_control_recovers_known_weights():
    panel, event_time, _ = make_synthetic_panel()

    weights, pre_rmse = fit_synthetic_control(
        panel, "TREATED", ["DONOR_A", "DONOR_B", "DONOR_C"], event_time
    )

    assert weights["DONOR_A"] == pytest.approx(0.6, abs=0.1)
    assert weights["DONOR_B"] == pytest.approx(0.4, abs=0.1)
    assert weights["DONOR_C"] == pytest.approx(0.0, abs=0.1)
    assert abs(weights.sum() - 1.0) < 1e-6
    assert (weights >= 0).all()
    assert pre_rmse < 0.01  # should fit near-perfectly since treated is an exact combo pre-period


def test_estimate_effect_detects_injected_gap():
    panel, event_time, post_end = make_synthetic_panel()
    weights, _ = fit_synthetic_control(panel, "TREATED", ["DONOR_A", "DONOR_B", "DONOR_C"], event_time)

    effect = estimate_effect(panel, "TREATED", weights, event_time, post_end)

    assert effect["mean_gap"] == pytest.approx(0.01, abs=0.005)


def test_pre_period_correlation_is_high_for_related_donors():
    panel, event_time, _ = make_synthetic_panel()

    corr = pre_period_correlation(panel, "TREATED", ["DONOR_A", "DONOR_B", "DONOR_C"], event_time)

    assert corr["DONOR_A"] > 0.8
    assert corr["DONOR_B"] > 0.8


def test_build_panel_aligns_multiple_symbols_on_open_time():
    df_a = pd.DataFrame(
        {
            "open_time": pd.to_datetime(["2024-06-01", "2024-06-02"], utc=True),
            "high": [110.0, 111.0],
            "low": [90.0, 91.0],
            "close": [100.0, 101.0],
        }
    )
    df_b = pd.DataFrame(
        {
            "open_time": pd.to_datetime(["2024-06-01", "2024-06-02"], utc=True),
            "high": [210.0, 211.0],
            "low": [190.0, 191.0],
            "close": [200.0, 201.0],
        }
    )

    panel = build_panel({"A": df_a, "B": df_b})

    assert list(panel.columns) == ["A", "B"]
    assert len(panel) == 2
