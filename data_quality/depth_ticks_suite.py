"""Great Expectations suite for the raw depth_ticks table.

Catches corruption that would silently produce a wrong order book or wrong downstream
features if it ever reached dbt unnoticed - e.g. ask < bid, negative spread, nulls in
fields every downstream model assumes are always present.
"""
from __future__ import annotations

import great_expectations as gx
import pandas as pd


def build_suite() -> gx.ExpectationSuite:
    suite = gx.ExpectationSuite(name="depth_ticks_suite")
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="ts_ms"))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="best_bid"))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="best_ask"))
    suite.add_expectation(
        gx.expectations.ExpectColumnPairValuesAToBeGreaterThanB(
            column_A="best_ask", column_B="best_bid", or_equal=False
        )
    )
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeBetween(column="spread", min_value=0))
    return suite


def validate(df: pd.DataFrame):
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name="pandas_ds")
    data_asset = data_source.add_dataframe_asset(name="depth_ticks")
    batch_definition = data_asset.add_batch_definition_whole_dataframe("batch_def")
    batch = batch_definition.get_batch(batch_parameters={"dataframe": df})
    return batch.validate(build_suite())
