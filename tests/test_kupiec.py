import pytest

from risk.kupiec import kupiec_test


def test_fails_to_reject_when_violation_rate_matches_expected():
    # 95% VaR over 1000 observations should expect ~50 violations
    result = kupiec_test(n_observations=1000, n_violations=50, confidence=0.95)

    assert result["expected_violations"] == pytest.approx(50.0)
    assert result["p_value"] > 0.05
    assert result["reject_null_at_5pct"] is False
    assert "FAIL TO REJECT" in result["conclusion"]


def test_rejects_when_violation_rate_way_off_expected():
    # way more violations than expected at 95% confidence -> model is too tight/miscalibrated
    result = kupiec_test(n_observations=1000, n_violations=200, confidence=0.95)

    assert result["p_value"] < 0.05
    assert result["reject_null_at_5pct"] is True
    assert "REJECT" in result["conclusion"]


def test_handles_zero_violations_without_error():
    result = kupiec_test(n_observations=100, n_violations=0, confidence=0.95)
    assert result["violation_rate"] == 0.0
    assert result["lr_statistic"] >= 0


def test_handles_all_violations_without_error():
    result = kupiec_test(n_observations=10, n_violations=10, confidence=0.95)
    assert result["violation_rate"] == 1.0
    assert result["lr_statistic"] >= 0
