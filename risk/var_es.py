"""Rolling historical VaR and Expected Shortfall on a P&L series.

Historical simulation method: no distributional assumption, just empirical quantiles of a
rolling window of P&L changes. Both are reported as positive numbers (loss magnitudes).
"""
from __future__ import annotations

import pandas as pd


def rolling_var_es(pnl: pd.Series, window: int, confidence: float = 0.95) -> pd.DataFrame:
    """VaR = the `confidence`-quantile of the loss distribution over a trailing window.
    ES = the average loss beyond VaR (average of the worst 1-confidence fraction of losses).

    By construction ES >= VaR at every point (ES averages a tail that is entirely >= VaR).
    """
    losses = -pnl.diff()

    var = losses.rolling(window).quantile(confidence)
    es = losses.rolling(window).apply(
        lambda x: x[x >= x.quantile(confidence)].mean(), raw=False
    )

    return pd.DataFrame({"var": var, "es": es})
