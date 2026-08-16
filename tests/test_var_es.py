import numpy as np
import pandas as pd
import pytest

from risk.var_es import rolling_var_es


def test_es_is_always_at_least_var():
    rng = np.random.default_rng(0)
    pnl = pd.Series(np.cumsum(rng.standard_normal(500)))

    result = rolling_var_es(pnl, window=50, confidence=0.95).dropna()

    assert (result["es"] >= result["var"] - 1e-9).all()


def test_es_captures_tail_severity_that_var_misses_at_the_boundary():
    # 100 P&L steps: 95 small gains of +1, then 5 big drops of -10 - exactly the 95%
    # confidence level, so the tail is exactly 5% of the sample.
    steps = [1] * 95 + [-10] * 5
    pnl = pd.Series(np.concatenate([[0], np.cumsum(steps)]))  # cumulative P&L level series
    result = rolling_var_es(pnl, window=100, confidence=0.95)

    last_var = result["var"].iloc[-1]
    last_es = result["es"].iloc[-1]

    # This is the real point of ES over VaR: with the tail at exactly 5%, the 95th
    # percentile (VaR) sits right at the "safe" -1 losses and barely registers the tail
    # at all, while ES - the average of the worst 5% - correctly captures the severe -10
    # losses. VaR alone would badly understate risk here; ES doesn't.
    assert last_var < 1.0
    assert last_es == pytest.approx(10.0, abs=0.01)
    assert last_es >= last_var
    assert last_es > last_var + 5  # ES dramatically exceeds VaR at this exact boundary


def test_rolling_var_es_has_nan_before_window_fills():
    pnl = pd.Series(np.arange(10, dtype=float))
    result = rolling_var_es(pnl, window=5, confidence=0.95)
    assert result["var"].iloc[:4].isna().all()
