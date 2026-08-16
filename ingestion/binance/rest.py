"""Fetches an order-book snapshot from Binance's REST API.

Used to bootstrap and resync the local OrderBook per Binance's documented procedure:
https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams (Diff. Depth Stream)
"""
from __future__ import annotations

import requests

BASE_URL = "https://api.binance.com/api/v3/depth"


def fetch_depth_snapshot(symbol: str, limit: int = 1000) -> dict:
    """symbol like 'BTCUSDT' (uppercase, no separator). Returns dict with lastUpdateId, bids, asks."""
    response = requests.get(BASE_URL, params={"symbol": symbol.upper(), "limit": limit}, timeout=10)
    response.raise_for_status()
    return response.json()
