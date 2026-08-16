"""Loads the local Parquet tick lake into a warehouse: DuckDB for dev, BigQuery for prod.

Raw tables are always a full mirror of the lake (CREATE OR REPLACE / WRITE_TRUNCATE) -
no incremental logic here. Incremental/derived logic belongs in dbt models, not the loader.

Usage:
    python -m warehouse.load_raw --target dev
    python -m warehouse.load_raw --target prod
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

TABLES = ["depth_ticks", "trades"]
DEFAULT_LAKE_ROOT = Path("data/lake")


def read_table_as_dataframe(lake_root: Path, table: str, symbol: str) -> pd.DataFrame:
    partition_dir = lake_root / table / f"symbol={symbol.upper()}"
    files = sorted(partition_dir.glob("date=*/*.parquet"))
    if not files:
        raise FileNotFoundError(f"No Parquet files found under {partition_dir}")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def load_to_duckdb(lake_root: Path, duckdb_path: Path, symbol: str) -> None:
    import duckdb

    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(duckdb_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    for table in TABLES:
        partition_dir = lake_root / table / f"symbol={symbol.upper()}"
        glob_path = (partition_dir / "date=*" / "*.parquet").as_posix()
        con.execute(f"CREATE OR REPLACE TABLE raw.{table} AS SELECT * FROM read_parquet('{glob_path}')")
        count = con.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]
        print(f"[duckdb] raw.{table}: {count} rows")
    con.close()


def load_to_bigquery(lake_root: Path, project_id: str, dataset: str, symbol: str) -> None:
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    for table in TABLES:
        df = read_table_as_dataframe(lake_root, table, symbol)
        table_ref = f"{project_id}.{dataset}.raw_{table}"
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
        job.result()
        print(f"[bigquery] {table_ref}: {len(df)} rows")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["dev", "prod"], required=True)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--lake-root", default=str(DEFAULT_LAKE_ROOT))
    parser.add_argument("--duckdb-path", default="dbt/dev.duckdb")
    parser.add_argument("--project-id", default="optimum-bonbon-296801")
    parser.add_argument("--dataset", default="market_data")
    args = parser.parse_args()

    lake_root = Path(args.lake_root)

    if args.target == "dev":
        load_to_duckdb(lake_root, Path(args.duckdb_path), args.symbol)
    else:
        load_to_bigquery(lake_root, args.project_id, args.dataset, args.symbol)


if __name__ == "__main__":
    main()
