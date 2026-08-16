"""Operational risk check: pulls recent data from BigQuery, computes rolling VaR/ES,
backtests the VaR model with Kupiec, and fires alerts if something looks wrong.

Meant to be called from Airflow on a schedule (see dags/microstructure_pipeline.py).
Exits non-zero if any CRITICAL alert fires, so the DAG task can fail loudly.

Scope note: there's no continuously-running paper-trading position tracker in this project,
so the inventory-limit alert check (implemented and tested in risk/alerts.py) isn't wired
into this live check - there's no real "current inventory" to check it against. VaR/ES here
run on a simple long-1-unit mark-to-market P&L proxy built from mid_price, not a strategy's
actual P&L.

Usage: python -m risk.run_risk_checks [--project-id ID] [--dataset NAME]
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

from risk.alerts import check_toxic_flow, check_var_breach
from risk.kupiec import kupiec_test
from risk.var_es import rolling_var_es

VAR_RESAMPLE_INTERVAL = "1min"
VAR_WINDOW = 60  # 60 one-minute bars = 1 trailing hour
VAR_CONFIDENCE = 0.95


def fetch_recent_depth_features(client: bigquery.Client, project_id: str, dataset: str) -> pd.DataFrame:
    query = f"""
        select event_time, mid_price
        from `{project_id}.{dataset}.fct_depth_features`
        order by event_time
    """
    return client.query(query).to_dataframe()


def fetch_latest_vpin_regime(client: bigquery.Client, project_id: str, dataset: str) -> str:
    query = f"""
        select vpin_regime
        from `{project_id}.{dataset}.fct_vpin`
        order by bucket_end_time desc
        limit 1
    """
    rows = list(client.query(query).result())
    return rows[0]["vpin_regime"] if rows else "normal"


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", default="optimum-bonbon-296801")
    parser.add_argument("--dataset", default="market_data")
    args = parser.parse_args()

    client = bigquery.Client(project=args.project_id)

    depth = fetch_recent_depth_features(client, args.project_id, args.dataset)

    # Resample to a fixed clock-time grid before computing P&L - NOT raw event-time ticks, and
    # NOT a too-fine grid either. BTC/USDT's mid-price is literally unchanged in ~99.5% of
    # 1-second intervals (it's that liquid), so a 1s (or raw event-time) rolling quantile VaR
    # trivially collapses to ~0 in almost every window and then fails Kupiec - confirmed live:
    # 1s and 10s bars both reject (far fewer violations than expected, i.e. VaR too
    # conservative to be meaningful), while 1min and 5min bars - where genuine price variation
    # exists per bar - both pass cleanly. 1min is used here as the smallest interval where the
    # model is actually well-calibrated, not the finest interval technically available.
    mid = depth.set_index("event_time")["mid_price"].resample(VAR_RESAMPLE_INTERVAL).last().ffill()

    if len(mid) < VAR_WINDOW + 1:
        print(f"Not enough data for a {VAR_WINDOW}-observation VaR window ({len(mid)} rows) - skipping.")
        return 0

    # mark-to-market P&L of a hypothetical long-1-unit position, as a simple risk proxy
    pnl = mid

    var_es = rolling_var_es(pnl, window=VAR_WINDOW, confidence=VAR_CONFIDENCE).dropna()
    losses = -pnl.diff().loc[var_es.index]
    violations = (losses > var_es["var"]).sum()

    kupiec = kupiec_test(n_observations=len(var_es), n_violations=int(violations), confidence=VAR_CONFIDENCE)
    print(f"Kupiec test: {kupiec['n_violations']}/{kupiec['n_observations']} violations "
          f"(expected {kupiec['expected_violations']:.1f}), p={kupiec['p_value']:.4f} -> {kupiec['conclusion']}")

    latest_var = var_es["var"].iloc[-1]
    latest_pnl_change = pnl.diff().iloc[-1]
    vpin_regime = fetch_latest_vpin_regime(client, args.project_id, args.dataset)
    print(f"Latest VaR: {latest_var:.4f}, latest P&L change: {latest_pnl_change:.4f}, VPIN regime: {vpin_regime}")

    alerts = [
        alert
        for alert in [check_var_breach(latest_pnl_change, latest_var), check_toxic_flow(vpin_regime)]
        if alert is not None
    ]

    for alert in alerts:
        print(f"[{alert.severity.upper()}] {alert.rule}: {alert.message}")

    critical = [a for a in alerts if a.severity == "critical"]
    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())
