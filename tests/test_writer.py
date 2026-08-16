from datetime import datetime, timezone

import pyarrow.parquet as pq

from ingestion.binance.writer import TickWriter


def ts_ms(year, month, day, hour=0):
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp() * 1000)


def test_flush_writes_partitioned_parquet_with_matching_row_count(tmp_path):
    writer = TickWriter("depth_ticks", "BTCUSDT", lake_root=tmp_path, flush_every=1000)

    writer.add({"ts_ms": ts_ms(2026, 8, 16), "best_bid": 100.0, "best_ask": 100.5})
    writer.add({"ts_ms": ts_ms(2026, 8, 16, hour=23), "best_bid": 101.0, "best_ask": 101.5})
    writer.flush()

    partition_dir = tmp_path / "depth_ticks" / "symbol=BTCUSDT" / "date=2026-08-16"
    files = list(partition_dir.glob("*.parquet"))
    assert len(files) == 1

    table = pq.read_table(files[0])
    assert table.num_rows == 2
    assert sorted(table.column("best_bid").to_pylist()) == [100.0, 101.0]


def test_rows_on_different_dates_land_in_different_partitions(tmp_path):
    writer = TickWriter("trades", "ETHUSDT", lake_root=tmp_path, flush_every=1000)

    writer.add({"ts_ms": ts_ms(2026, 8, 16), "price": 1.0})
    writer.add({"ts_ms": ts_ms(2026, 8, 17), "price": 2.0})
    writer.flush()

    day1 = tmp_path / "trades" / "symbol=ETHUSDT" / "date=2026-08-16"
    day2 = tmp_path / "trades" / "symbol=ETHUSDT" / "date=2026-08-17"
    assert len(list(day1.glob("*.parquet"))) == 1
    assert len(list(day2.glob("*.parquet"))) == 1


def test_auto_flush_triggers_at_threshold(tmp_path):
    writer = TickWriter("trades", "BTCUSDT", lake_root=tmp_path, flush_every=3)

    for _ in range(3):
        writer.add({"ts_ms": ts_ms(2026, 8, 16), "price": 1.0})

    assert len(writer) == 0  # auto-flushed, buffer cleared
    partition_dir = tmp_path / "trades" / "symbol=BTCUSDT" / "date=2026-08-16"
    assert len(list(partition_dir.glob("*.parquet"))) == 1
