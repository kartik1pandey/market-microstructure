"""Entry point: runs the Binance stream and writes ticks to a lake backend.

Usage: python -m ingestion.binance.main [SYMBOL]
Stop with Ctrl+C - buffered rows are flushed before exit.

Backend is chosen via the LAKE_BACKEND env var:
- "parquet" (default): local Parquet lake, for local dev - see writer.py
- "bigquery": streams straight to BigQuery, for continuous cloud deployment (e.g. Render),
  where the local filesystem is ephemeral - see bigquery_writer.py. Needs GCP_PROJECT_ID and
  BIGQUERY_DATASET env vars, plus GOOGLE_APPLICATION_CREDENTIALS pointing at a service account key.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from .stream import BinanceStream
from .writer import TickWriter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEPTH_LEVELS = 5


def build_writer(table_name: str, symbol: str):
    backend = os.environ.get("LAKE_BACKEND", "parquet")
    if backend == "bigquery":
        from .bigquery_writer import BigQueryTickWriter

        return BigQueryTickWriter(
            table_name,
            symbol,
            project_id=os.environ["GCP_PROJECT_ID"],
            dataset=os.environ["BIGQUERY_DATASET"],
        )
    return TickWriter(table_name, symbol)


async def run(symbol: str) -> None:
    depth_writer = build_writer("depth_ticks", symbol)
    trade_writer = build_writer("trades", symbol)

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
    load_dotenv()
    target_symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    try:
        asyncio.run(run(target_symbol))
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
