import pandas as pd

from data_quality.depth_ticks_suite import validate


def good_df():
    return pd.DataFrame(
        {
            "ts_ms": [1, 2, 3],
            "best_bid": [100.0, 101.0, 102.0],
            "best_ask": [100.5, 101.5, 102.5],
            "spread": [0.5, 0.5, 0.5],
        }
    )


def test_suite_passes_on_clean_data():
    result = validate(good_df())
    assert result.success


def test_suite_fails_when_ask_is_below_bid():
    df = good_df()
    df.loc[2, "best_ask"] = 99.0  # inject: ask < bid on the last row
    df.loc[2, "spread"] = -3.0

    result = validate(df)

    assert not result.success
    failed_types = {r.expectation_config.type for r in result.results if not r.success}
    assert "expect_column_pair_values_a_to_be_greater_than_b" in failed_types
    assert "expect_column_values_to_be_between" in failed_types


def test_suite_fails_on_null_best_bid():
    df = good_df()
    df.loc[1, "best_bid"] = None

    result = validate(df)

    assert not result.success
