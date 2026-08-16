import numpy as np
import pandas as pd

from risk.attribution import MIN_SAMPLE_SIZE, attribute_pnl_by_vpin_regime


def test_attribution_detects_worse_pnl_during_toxic_regime():
    rng = np.random.default_rng(0)
    n = 300
    times = pd.date_range("2026-01-01", periods=n, freq="s", tz="utc")

    # regimes: first third normal, second third elevated, last third toxic
    regime_bounds = [times[0], times[n // 3], times[2 * n // 3]]
    vpin_df = pd.DataFrame(
        {"bucket_end_time": regime_bounds, "vpin_regime": ["normal", "elevated", "toxic"]}
    )

    # P&L changes: positive drift in normal, near-zero in elevated, negative drift in toxic
    changes = np.concatenate(
        [
            0.1 + 0.01 * rng.standard_normal(n // 3),
            0.0 + 0.01 * rng.standard_normal(n // 3),
            -0.2 + 0.01 * rng.standard_normal(n - 2 * (n // 3)),
        ]
    )
    pnl_levels = np.concatenate([[0], np.cumsum(changes)])
    pnl_df = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=n + 1, freq="s", tz="utc"), "pnl": pnl_levels})

    result = attribute_pnl_by_vpin_regime(pnl_df, vpin_df)

    assert result.loc["normal", "mean"] > result.loc["elevated", "mean"]
    assert result.loc["elevated", "mean"] > result.loc["toxic", "mean"]
    assert result.loc["toxic", "mean"] < 0
    assert result["reliable"].all()  # 100 observations per regime, well above MIN_SAMPLE_SIZE


def test_attribution_flags_small_samples_as_unreliable():
    vpin_df = pd.DataFrame(
        {
            "bucket_end_time": pd.to_datetime(["2026-01-01 00:00:00", "2026-01-01 00:00:05"], utc=True),
            "vpin_regime": ["normal", "toxic"],
        }
    )
    # only 3 pnl observations total - nowhere near MIN_SAMPLE_SIZE
    pnl_df = pd.DataFrame(
        {
            "time": pd.to_datetime(
                ["2026-01-01 00:00:01", "2026-01-01 00:00:02", "2026-01-01 00:00:06"], utc=True
            ),
            "pnl": [0.0, 1.0, 2.0],
        }
    )

    result = attribute_pnl_by_vpin_regime(pnl_df, vpin_df)

    assert not result["reliable"].any()
    assert (result["count"] < MIN_SAMPLE_SIZE).all()
