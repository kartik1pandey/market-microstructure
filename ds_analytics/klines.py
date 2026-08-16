"""Fetches historical OHLCV klines from Binance's public REST API (no auth needed).

Used for the DS-analytics event study, which needs a pre-period baseline stretching
before our own live L2 capture began - klines are the only history available that far back.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import requests

BASE_URL = "https://api.binance.com/api/v3/klines"
MAX_LIMIT = 1000

RAW_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "num_trades", "taker_buy_base_volume", "taker_buy_quote_volume", "ignore",
]


def to_ms(date_str: str) -> int:
    return int(datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc).timestamp() * 1000)


def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Paginates through Binance's 1000-candle-per-request limit to cover the full range."""
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        response = requests.get(
            BASE_URL,
            params={
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": MAX_LIMIT,
            },
            timeout=10,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + 1
        if len(batch) < MAX_LIMIT:
            break
        time.sleep(0.2)

    df = pd.DataFrame(rows, columns=RAW_COLUMNS)
    if df.empty:
        return df

    numeric_cols = ["open", "high", "low", "close", "volume", "quote_volume",
                     "taker_buy_base_volume", "taker_buy_quote_volume"]
    df[numeric_cols] = df[numeric_cols].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["symbol"] = symbol
    return df[["symbol", "open_time", "open", "high", "low", "close", "volume",
               "quote_volume", "num_trades"]]
