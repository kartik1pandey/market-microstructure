"""VPIN-based P&L attribution: does market-making P&L differ systematically across
VPIN regimes (normal/elevated/toxic)?

The hypothesis this tests: a passive market maker should do worse (more adverse selection)
when VPIN signals informed/toxic flow, since it's more likely to get run over by directional,
better-informed order flow in those periods.
"""
from __future__ import annotations

import pandas as pd

MIN_SAMPLE_SIZE = 10  # don't trust a regime comparison with fewer than this many observations


def attribute_pnl_by_vpin_regime(pnl_df: pd.DataFrame, vpin_df: pd.DataFrame) -> pd.DataFrame:
    """pnl_df needs columns: time, pnl (a mark-to-market P&L level series over time).
    vpin_df needs columns: bucket_end_time, vpin_regime.

    Matches each pnl row to the most recent VPIN regime at/before its time, then reports
    mean per-step P&L change and sample size per regime, flagging regimes with too few
    observations to trust the comparison.
    """
    pnl = pnl_df.sort_values("time").reset_index(drop=True).copy()
    vpin = vpin_df.sort_values("bucket_end_time").reset_index(drop=True).copy()

    merged = pd.merge_asof(
        pnl, vpin[["bucket_end_time", "vpin_regime"]], left_on="time", right_on="bucket_end_time", direction="backward"
    )
    merged["pnl_change"] = merged["pnl"].diff()

    grouped = merged.groupby("vpin_regime", observed=True)["pnl_change"].agg(mean="mean", count="count", std="std")
    grouped["reliable"] = grouped["count"] >= MIN_SAMPLE_SIZE
    return grouped
