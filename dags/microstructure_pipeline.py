"""Orchestrates the batch feature-computation pipeline: load raw ticks, validate them,
run dbt, test dbt. Ingestion itself runs continuously outside Airflow (it's a long-lived
streaming process, not a batch job) - this DAG only handles the scheduled batch transform.

Order matters: the data-quality gate runs on the RAW data before dbt transforms it, so a
corrupt row is caught right where it entered the pipeline, not several models downstream.

Two lanes after the shared GE gate: dev (DuckDB, fast local iteration) and prod (BigQuery,
which the Looker Studio dashboard reads from AND which the risk check queries).

IMPORTANT: the prod lane does NOT run warehouse.load_raw anymore. Once the cloud ingestion
worker (ingestion/binance/bigquery_writer.py, deployed on Render) is live, it streams
straight into the prod raw_depth_ticks/raw_trades tables continuously - running the local
loader against prod would CREATE OR REPLACE those tables from the local (dev-machine) lake
and destroy everything the cloud worker has appended. The prod lane here only transforms
whatever's already in BigQuery.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/opt/airflow/project"
DBT_DIR = f"{PROJECT_DIR}/dbt"

default_args = {
    "owner": "market-microstructure",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="microstructure_pipeline",
    description="Load raw ticks -> GE checkpoint -> dbt run -> dbt test",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 8, 1),
    catchup=False,
    default_args=default_args,
    tags=["market-microstructure"],
) as dag:

    load_raw = BashOperator(
        task_id="load_raw",
        bash_command=f"cd {PROJECT_DIR} && python -m warehouse.load_raw --target dev",
    )

    ge_checkpoint = BashOperator(
        task_id="ge_checkpoint",
        bash_command=f"cd {PROJECT_DIR} && python -m data_quality.run_checkpoint",
    )

    # --no-partial-parse: the target/ dir (with its partial-parse cache) is shared via the
    # host bind mount, and a cache built on the host can go stale relative to a container
    # run (or vice versa) - simpler to always parse fresh than debug that class of bug.
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {DBT_DIR} && dbt --no-partial-parse run --profiles-dir . --target dev",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_DIR} && dbt --no-partial-parse test --profiles-dir . --target dev",
    )

    dbt_run_prod = BashOperator(
        task_id="dbt_run_prod",
        bash_command=f"cd {DBT_DIR} && dbt --no-partial-parse run --profiles-dir . --target prod",
    )

    dbt_test_prod = BashOperator(
        task_id="dbt_test_prod",
        bash_command=f"cd {DBT_DIR} && dbt --no-partial-parse test --profiles-dir . --target prod",
    )

    risk_check = BashOperator(
        task_id="risk_check",
        bash_command=f"cd {PROJECT_DIR} && python -m risk.run_risk_checks",
    )

    load_raw >> ge_checkpoint >> dbt_run >> dbt_test
    ge_checkpoint >> dbt_run_prod >> dbt_test_prod >> risk_check
