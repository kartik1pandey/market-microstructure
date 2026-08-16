import asyncio
import json
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


class _RaisingConnection:
    """Simulates websockets.connect() failing to establish/hold a connection."""

    async def __aenter__(self):
        raise OSError("simulated dropped connection")

    async def __aexit__(self, *exc_info):
        return False


class _WorkingConnection:
    """Simulates a healthy connection that yields a couple of messages, then idles."""

    def __init__(self, messages):
        self._messages = messages

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def __aiter__(self):
        return self._generator()

    async def _generator(self):
        for message in self._messages:
            yield message
        await asyncio.Event().wait()  # then hold the connection open indefinitely


def test_run_reconnects_after_dropped_connection_and_resyncs():
    fake_snapshot = {
        "lastUpdateId": 100,
        "bids": [["100.00", "1.0"]],
        "asks": [["100.50", "1.0"]],
    }
    depth_event = {"stream": "btcusdt@depth@100ms", "data": {"e": "depthUpdate", "U": 101, "u": 101, "b": [], "a": []}}

    connect_calls = []

    def fake_connect(url):
        connect_calls.append(url)
        if len(connect_calls) == 1:
            return _RaisingConnection()
        return _WorkingConnection([json.dumps(depth_event)])

    async def scenario():
        stream = make_stream()
        with patch("ingestion.binance.stream.websockets.connect", side_effect=fake_connect), patch(
            "ingestion.binance.stream.fetch_depth_snapshot", return_value=fake_snapshot
        ), patch("ingestion.binance.stream.asyncio.sleep", return_value=None):
            try:
                await asyncio.wait_for(stream.run(), timeout=1)
            except asyncio.TimeoutError:
                pass
        return stream

    stream = run(scenario())

    assert len(connect_calls) == 2  # first attempt failed, second succeeded
    assert stream.book.last_update_id == 101  # resynced and applied the event after reconnecting
