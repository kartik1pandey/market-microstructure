"""Kupiec (1995) proportion-of-failures likelihood-ratio test for VaR model validation.

H0: the true VaR-violation rate equals the nominal (1 - confidence) rate. Rejecting H0
means the VaR model is miscalibrated - violating too often (model too tight) or too rarely
(model too loose, wasting capital on unnecessary buffer).
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def kupiec_test(n_observations: int, n_violations: int, confidence: float = 0.95) -> dict:
    p = 1 - confidence
    p_hat = n_violations / n_observations

    def log_likelihood(violation_rate: float) -> float:
        # 0*log(0) is conventionally 0, not -inf/nan - handle the boundary rates explicitly.
        if violation_rate <= 0:
            return 0.0 if n_violations == 0 else -np.inf
        if violation_rate >= 1:
            return 0.0 if n_violations == n_observations else -np.inf
        return (n_observations - n_violations) * np.log(1 - violation_rate) + n_violations * np.log(
            violation_rate
        )

    log_likelihood_null = log_likelihood(p)
    log_likelihood_alt = log_likelihood(p_hat)

    lr_stat = -2 * (log_likelihood_null - log_likelihood_alt)
    p_value = float(1 - stats.chi2.cdf(lr_stat, df=1))
    reject = p_value < 0.05

    return {
        "n_observations": n_observations,
        "n_violations": n_violations,
        "expected_violations": n_observations * p,
        "violation_rate": p_hat,
        "lr_statistic": float(lr_stat),
        "p_value": p_value,
        "reject_null_at_5pct": reject,
        "conclusion": (
            "REJECT: violation rate significantly differs from expected - VaR model may be miscalibrated"
            if reject
            else "FAIL TO REJECT: violation rate consistent with expected - no evidence of miscalibration"
        ),
    }
