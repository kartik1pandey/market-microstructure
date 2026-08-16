"""Entry point: runs the Binance stream and writes ticks to the local Parquet lake.

Usage: python -m ingestion.binance.main [SYMBOL]
Stop with Ctrl+C - buffered rows are flushed before exit.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from .stream import BinanceStream
from .writer import TickWriter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEPTH_LEVELS = 5


async def run(symbol: str) -> None:
    depth_writer = TickWriter("depth_ticks", symbol)
    trade_writer = TickWriter("trades", symbol)

    async def on_depth(book, event):
        bid_prices, bid_qtys, ask_prices, ask_qtys = book.top_levels(DEPTH_LEVELS)
        depth_writer.add(
            {
                "ts_ms": event["E"],
                "first_update_id": event["U"],
                "final_update_id": event["u"],
                "best_bid": book.best_bid,
                "best_ask": book.best_ask,
                "spread": book.spread,
                "bid_prices": bid_prices,
                "bid_qtys": bid_qtys,
                "ask_prices": ask_prices,
                "ask_qtys": ask_qtys,
            }
        )

    async def on_trade(event):
        trade_writer.add(
            {
                "ts_ms": event["T"],
                "trade_id": event["t"],
                "price": float(event["p"]),
                "qty": float(event["q"]),
                "is_buyer_maker": event["m"],
            }
        )

    stream = BinanceStream(symbol, on_depth, on_trade)
    try:
        logger.info("Starting ingestion for %s", symbol)
        await stream.run()
    finally:
        depth_writer.flush()
        trade_writer.flush()
        logger.info("Flushed buffers on shutdown.")


if __name__ == "__main__":
    target_symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    try:
        asyncio.run(run(target_symbol))
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
