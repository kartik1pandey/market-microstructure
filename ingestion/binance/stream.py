"""WebSocket connector for Binance's combined depth-diff + trade streams.

Implements Binance's documented resync procedure: buffer diffs, apply a REST snapshot,
replay the buffer, then apply live diffs directly - resyncing from a fresh snapshot
whenever a sequence gap or disconnect occurs. Never trust book state across a reconnect.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

import websockets

from .orderbook import OrderBook, SequenceGapError
from .rest import fetch_depth_snapshot

logger = logging.getLogger(__name__)

COMBINED_STREAM_URL = "wss://stream.binance.com:9443/stream?streams={streams}"
MAX_BACKOFF_SECONDS = 60
SYNC_RETRY_INTERVAL = 20  # once buffer is large, only retry the snapshot fetch every Nth event

DepthCallback = Callable[[OrderBook, dict], Awaitable[None]]
TradeCallback = Callable[[dict], Awaitable[None]]


class BinanceStream:
    def __init__(self, symbol: str, on_depth_event: DepthCallback, on_trade_event: TradeCallback):
        self.symbol = symbol.lower()
        self.on_depth_event = on_depth_event
        self.on_trade_event = on_trade_event
        self.book = OrderBook(symbol=symbol.upper())

    def _stream_url(self) -> str:
        streams = f"{self.symbol}@depth@100ms/{self.symbol}@trade"
        return COMBINED_STREAM_URL.format(streams=streams)

    async def run(self) -> None:
        """Connect and process forever, reconnecting with exponential backoff on failure."""
        backoff = 1
        while True:
            try:
                # Fresh OrderBook on every (re)connect - never trust a book we weren't watching.
                self.book = OrderBook(symbol=self.symbol.upper())
                await self._connect_and_process()
                backoff = 1
            except (websockets.exceptions.ConnectionClosed, OSError) as exc:
                logger.warning("Connection lost (%s); reconnecting in %ss", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def _connect_and_process(self) -> None:
        async with websockets.connect(self._stream_url()) as ws:
            queue: asyncio.Queue = asyncio.Queue()

            async def producer() -> None:
                async for raw in ws:
                    await queue.put(json.loads(raw)["data"])

            producer_task = asyncio.create_task(producer())
            try:
                await self._consume(queue)
            finally:
                producer_task.cancel()

    async def _consume(self, queue: asyncio.Queue) -> None:
        buffer: list[dict] = []
        synced = False

        while True:
            data = await queue.get()
            event_type = data.get("e")

            if event_type == "trade":
                await self.on_trade_event(data)
                continue

            if event_type != "depthUpdate":
                continue

            if not synced:
                buffer.append(data)
                if len(buffer) == 1 or len(buffer) % SYNC_RETRY_INTERVAL == 0:
                    remaining = await self._try_sync(buffer)
                    if remaining is not None:
                        for event in remaining:
                            await self.on_depth_event(self.book, event)
                        synced = True
                        buffer.clear()
                continue

            try:
                self.book.apply_diff(data)
                await self.on_depth_event(self.book, data)
            except SequenceGapError as exc:
                logger.warning("Sequence gap (%s); resyncing", exc)
                synced = False
                buffer = [data]

    async def _try_sync(self, buffer: list[dict]) -> list[dict] | None:
        """Fetch a snapshot and align it against the buffer per Binance's resync procedure.

        Returns the buffered events that land on top of the snapshot (already applied to
        self.book), or None if the snapshot is already stale relative to the buffer -
        caller should keep buffering and retry.
        """
        snapshot = await asyncio.to_thread(fetch_depth_snapshot, self.symbol.upper())
        last_update_id = snapshot["lastUpdateId"]

        remaining = [event for event in buffer if event["u"] > last_update_id]
        if remaining and remaining[0]["U"] > last_update_id + 1:
            return None

        self.book.apply_snapshot(snapshot)
        for event in remaining:
            self.book.apply_diff(event)
        return remaining
