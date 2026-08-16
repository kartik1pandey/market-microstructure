"""Reproduces the case study in case_study.md end to end.

Usage: python -m ds_analytics.run_analysis [--interval 1h|1d]
"""
from __future__ import annotations

import argparse
import json

from ds_analytics.event_study import (
    estimate_effect,
    fit_synthetic_control,
    build_panel,
    placebo_test,
    pre_period_correlation,
)
from ds_analytics.klines import fetch_klines, to_ms

TREATED = "BTCTUSD"
DONORS = ["BTCUSDT", "BTCUSDC", "BTCFDUSD"]
PRE_START = "2024-06-01T00:00:00"
EVENT_TIME = "2024-07-16T00:00:00"
POST_END = "2024-07-30T00:00:00"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", choices=["1h", "1d"], default="1h")
    args = parser.parse_args()

    start_ms = to_ms(PRE_START)
    end_ms = to_ms(POST_END)

    klines = {
        symbol: fetch_klines(symbol, args.interval, start_ms, end_ms)
        for symbol in [TREATED, *DONORS]
    }
    for symbol, df in klines.items():
        print(f"{symbol}: {len(df)} candles")

    panel = build_panel(klines)
    event_time = panel.index[panel.index >= EVENT_TIME][0]
    post_end = panel.index[panel.index <= POST_END][-1]

    corr = pre_period_correlation(panel, TREATED, DONORS, event_time)
    print(f"\nPre-period correlation:\n{corr}")

    weights, pre_rmse = fit_synthetic_control(panel, TREATED, DONORS, event_time)
    print(f"\nSynthetic control weights:\n{weights}")
    print(f"Pre-period RMSE: {pre_rmse}")

    effect = estimate_effect(panel, TREATED, weights, event_time, post_end)
    print(f"\nEffect estimate:\n{json.dumps(effect, indent=2)}")

    placebo = placebo_test(panel, TREATED, DONORS, event_time, post_end)
    print(f"\nPlacebo gaps:\n{json.dumps(placebo, indent=2)}")


if __name__ == "__main__":
    main()
