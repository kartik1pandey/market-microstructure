"""Runs the depth_ticks data-quality checkpoint against the local Parquet lake.

Usage: python -m data_quality.run_checkpoint [SYMBOL]
Exit code 0 on pass, 1 on failure - meant to gate the Airflow DAG before dbt runs.
"""
from __future__ import annotations

import sys

from data_quality.depth_ticks_suite import validate
from warehouse.load_raw import DEFAULT_LAKE_ROOT, read_table_as_dataframe


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    df = read_table_as_dataframe(DEFAULT_LAKE_ROOT, "depth_ticks", symbol)
    result = validate(df)

    print(f"Checkpoint on {len(df)} rows: {'PASS' if result.success else 'FAIL'}")
    for expectation_result in result.results:
        status = "OK" if expectation_result.success else "FAILED"
        print(f"  [{status}] {expectation_result.expectation_config.type}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
