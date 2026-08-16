"""Buffers ticks in memory and flushes them straight to BigQuery via an append load job.

Same interface as writer.TickWriter (add/flush/__len__), so main.py can swap between them
via an env var. Used for continuous cloud deployment (e.g. Render), where the local
filesystem is ephemeral - flushing straight to BigQuery means a worker restart only ever
loses the current unflushed buffer, never the whole history, since everything already
flushed is already durable in BigQuery.

Uses a batch LOAD job (WRITE_APPEND), not a streaming insert (tabledata.insertAll) - a real
constraint discovered by testing against the actual project: BigQuery Sandbox mode (no
billing account linked, which is what this project uses to stay genuinely free - see
docs/build-notes.md) rejects streaming inserts outright ("Streaming insert is not allowed in
the free tier"), but batch load jobs work fine in Sandbox mode, which is exactly what
warehouse/load_raw.py already relies on. flush_every defaults higher than the local Parquet
writer's 500 specifically to stay well under BigQuery's per-table daily load-job quota
(~1,500/day) even under frequent flushing.

Table names match warehouse/load_raw.py's convention (raw_depth_ticks, raw_trades) so dbt's
sources.yml needs no changes - but once this writer is live against a project, the local
warehouse.load_raw --target prod CREATE-OR-REPLACE loader must NOT be run against the same
project, or it will wipe out everything appended here.
"""
from __future__ import annotations

from google.cloud import bigquery

DEPTH_TICKS_SCHEMA = [
    bigquery.SchemaField("ts_ms", "INTEGER"),
    bigquery.SchemaField("first_update_id", "INTEGER"),
    bigquery.SchemaField("final_update_id", "INTEGER"),
    bigquery.SchemaField("best_bid", "FLOAT"),
    bigquery.SchemaField("best_ask", "FLOAT"),
    bigquery.SchemaField("spread", "FLOAT"),
    bigquery.SchemaField("bid_prices", "FLOAT", mode="REPEATED"),
    bigquery.SchemaField("bid_qtys", "FLOAT", mode="REPEATED"),
    bigquery.SchemaField("ask_prices", "FLOAT", mode="REPEATED"),
    bigquery.SchemaField("ask_qtys", "FLOAT", mode="REPEATED"),
]

TRADES_SCHEMA = [
    bigquery.SchemaField("ts_ms", "INTEGER"),
    bigquery.SchemaField("trade_id", "INTEGER"),
    bigquery.SchemaField("price", "FLOAT"),
    bigquery.SchemaField("qty", "FLOAT"),
    bigquery.SchemaField("is_buyer_maker", "BOOLEAN"),
]

SCHEMAS = {"depth_ticks": DEPTH_TICKS_SCHEMA, "trades": TRADES_SCHEMA}
TABLE_PREFIX = {"depth_ticks": "raw_depth_ticks", "trades": "raw_trades"}


class BigQueryTickWriter:
    def __init__(
        self,
        table_name: str,
        symbol: str,
        project_id: str,
        dataset: str,
        flush_every: int = 2000,
        client: bigquery.Client | None = None,
    ):
        self.table_name = table_name
        self.symbol = symbol.upper()
        self.flush_every = flush_every
        self._buffer: list[dict] = []

        self.client = client or bigquery.Client(project=project_id)
        self.table_ref = f"{project_id}.{dataset}.{TABLE_PREFIX[table_name]}"
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        table = bigquery.Table(self.table_ref, schema=SCHEMAS[self.table_name])
        self.client.create_table(table, exists_ok=True)

    def add(self, row: dict) -> None:
        self._buffer.append(row)
        if len(self._buffer) >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return

        # Don't clear self._buffer until the load job has actually succeeded - on failure
        # the unflushed rows stay put so a subsequent flush() can retry them, instead of
        # being silently dropped.
        rows_to_load = self._buffer

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            schema=SCHEMAS[self.table_name],
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )
        job = self.client.load_table_from_json(rows_to_load, self.table_ref, job_config=job_config)
        job.result()  # raises on failure

        self._buffer = []

    def __len__(self) -> int:
        return len(self._buffer)
