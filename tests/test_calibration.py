import numpy as np
import pandas as pd
import pytest

from alpha.calibration import calibrate_eta, calibrate_kappa, calibrate_sigma


def test_calibrate_sigma_recovers_known_volatility():
    rng = np.random.default_rng(0)
    n = 5000
    true_sigma_per_second = 0.0005

    timestamps_ms = np.arange(n) * 1000  # one tick per second
    log_returns = true_sigma_per_second * rng.standard_normal(n)
    prices = 100.0 * np.exp(np.cumsum(log_returns))

    depth_df = pd.DataFrame({"ts_ms": timestamps_ms, "mid_price": prices})

    estimated = calibrate_sigma(depth_df, sample_interval="1s")

    assert estimated == pytest.approx(true_sigma_per_second, rel=0.15)


def test_calibrate_kappa_recovers_known_decay():
    rng = np.random.default_rng(1)
    true_a = 50.0  # trades/second at delta=0
    true_kappa = 8.0
    time_span_seconds = 1000

    # Pick several delta levels, generate a trade count at each matching the theoretical
    # Poisson rate A*exp(-kappa*delta) over the time span, with timestamps spread across it.
    deltas = np.array([0.01, 0.02, 0.05, 0.08, 0.12, 0.16, 0.20])
    rows = []
    for delta in deltas:
        rate = true_a * np.exp(-true_kappa * delta)
        count = max(int(rate * time_span_seconds), 5)
        trade_times = rng.uniform(0, time_span_seconds * 1000, size=count)
        rows.append(pd.DataFrame({"ts_ms": trade_times, "delta": delta}))

    trades_raw = pd.concat(rows, ignore_index=True).sort_values("ts_ms").reset_index(drop=True)

    depth_df = pd.DataFrame({"ts_ms": [0, time_span_seconds * 1000], "mid_price": [100.0, 100.0]})
    trades_df = pd.DataFrame(
        {
            "ts_ms": trades_raw["ts_ms"],
            "price": 100.0 + trades_raw["delta"],  # always on the ask side, distance = delta
            "qty": 1.0,
        }
    )

    estimated_a, estimated_kappa = calibrate_kappa(trades_df, depth_df, n_bins=len(deltas))

    assert estimated_kappa == pytest.approx(true_kappa, rel=0.25)
    assert estimated_a == pytest.approx(true_a, rel=0.5)


def test_calibrate_eta_recovers_known_impact_coefficient():
    rng = np.random.default_rng(2)
    true_eta = 0.002
    n_buckets = 500

    net_volumes = rng.normal(0, 5, size=n_buckets)
    price_changes = true_eta * net_volumes + 0.0001 * rng.standard_normal(n_buckets)

    prices = 100.0 + np.cumsum(price_changes)
    timestamps_s = np.arange(n_buckets)

    depth_df = pd.DataFrame({"ts_ms": timestamps_s * 1000, "mid_price": prices})

    trade_rows = []
    for i, volume in enumerate(net_volumes):
        is_buy = volume >= 0
        qty = abs(volume) if volume != 0 else 0.001
        trade_rows.append(
            {
                "ts_ms": i * 1000 + 500,
                "price": prices[i],
                "qty": qty,
                "is_buyer_maker": not is_buy,  # buyer_maker=True means sell-initiated
            }
        )
    trades_df = pd.DataFrame(trade_rows)

    estimated_eta = calibrate_eta(trades_df, depth_df, bucket="1s")

    assert estimated_eta == pytest.approx(true_eta, rel=0.2)
