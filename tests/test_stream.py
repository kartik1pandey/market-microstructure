import asyncio
from unittest.mock import patch

from ingestion.binance.stream import BinanceStream


def run(coro):
    return asyncio.run(coro)


def make_stream():
    async def on_depth(book, event):
        pass

    async def on_trade(event):
        pass

    return BinanceStream("BTCUSDT", on_depth, on_trade)


def test_try_sync_applies_snapshot_and_contiguous_buffer():
    fake_snapshot = {
        "lastUpdateId": 100,
        "bids": [["100.00", "1.0"]],
        "asks": [["100.50", "1.0"]],
    }
    stale_event = {"U": 90, "u": 95, "b": [], "a": []}  # fully covered by the snapshot
    contiguous_event = {"U": 96, "u": 101, "b": [["99.90", "2.0"]], "a": []}
    buffer = [stale_event, contiguous_event]

    with patch("ingestion.binance.stream.fetch_depth_snapshot", return_value=fake_snapshot):
        stream = make_stream()
        remaining = run(stream._try_sync(buffer))

    assert remaining == [contiguous_event]
    assert stream.book.last_update_id == 101
    assert stream.book.best_bid == 100.00  # contiguous_event only added a lower bid


def test_try_sync_returns_none_when_snapshot_is_stale_relative_to_buffer():
    fake_snapshot = {
        "lastUpdateId": 100,
        "bids": [["100.00", "1.0"]],
        "asks": [["100.50", "1.0"]],
    }
    gapped_event = {"U": 150, "u": 160, "b": [], "a": []}  # gap: U=150 > lastUpdateId+1=101
    buffer = [gapped_event]

    with patch("ingestion.binance.stream.fetch_depth_snapshot", return_value=fake_snapshot):
        stream = make_stream()
        remaining = run(stream._try_sync(buffer))

    assert remaining is None
    assert stream.book.last_update_id is None  # snapshot was never applied
