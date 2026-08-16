"""Buffers ticks in memory and flushes them to local Parquet, partitioned by symbol/date.

This is the local-disk stand-in for "raw ticks land in S3 as Parquet" - same partitioning
scheme, same downstream dbt/BigQuery story, zero cloud dependency.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

DEFAULT_LAKE_ROOT = Path("data/lake")


class TickWriter:
    def __init__(
        self,
        table_name: str,
        symbol: str,
        lake_root: Path = DEFAULT_LAKE_ROOT,
        flush_every: int = 500,
    ):
        self.table_name = table_name
        self.symbol = symbol.upper()
        self.lake_root = lake_root
        self.flush_every = flush_every
        self._buffer: list[dict] = []

    def add(self, row: dict) -> None:
        """row must include a 'ts_ms' key (epoch milliseconds) used for date partitioning."""
        self._buffer.append(row)
        if len(self._buffer) >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return

        rows_by_date: dict[str, list[dict]] = {}
        for row in self._buffer:
            date_str = datetime.fromtimestamp(row["ts_ms"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            rows_by_date.setdefault(date_str, []).append(row)

        for date_str, rows in rows_by_date.items():
            partition_dir = (
                self.lake_root / self.table_name / f"symbol={self.symbol}" / f"date={date_str}"
            )
            partition_dir.mkdir(parents=True, exist_ok=True)

            table = pa.Table.from_pylist(rows)
            file_name = f"part-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.parquet"
            pq.write_table(table, partition_dir / file_name)

        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)
