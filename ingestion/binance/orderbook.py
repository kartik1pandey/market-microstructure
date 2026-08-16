"""Local limit-order-book reconstruction from a Binance diff-depth stream.

Follows Binance's documented procedure: apply a REST snapshot, then apply buffered
diff events on top, then keep applying new diffs as long as update IDs are contiguous.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from sortedcontainers import SortedDict


class SequenceGapError(Exception):
    """Raised when a diff event does not contiguously follow the last applied update ID."""


@dataclass
class OrderBook:
    symbol: str
    bids: SortedDict = field(default_factory=SortedDict)  # -price -> qty, so best bid sorts first
    asks: SortedDict = field(default_factory=SortedDict)  # price -> qty, so best ask sorts first
    last_update_id: int | None = None

    def apply_snapshot(self, snapshot: dict) -> None:
        """snapshot: {"lastUpdateId": int, "bids": [[price, qty], ...], "asks": [[price, qty], ...]}"""
        self.bids = SortedDict((-float(p), float(q)) for p, q in snapshot["bids"] if float(q) > 0)
        self.asks = SortedDict((float(p), float(q)) for p, q in snapshot["asks"] if float(q) > 0)
        self.last_update_id = snapshot["lastUpdateId"]

    def apply_diff(self, event: dict) -> None:
        """event: Binance depthUpdate message with keys U (first update id), u (final update id), b, a."""
        if self.last_update_id is None:
            raise SequenceGapError("No snapshot applied yet")

        first_update_id = event["U"]
        final_update_id = event["u"]

        if final_update_id <= self.last_update_id:
            return  # stale event, already covered by current state

        if first_update_id > self.last_update_id + 1:
            raise SequenceGapError(
                f"Gap detected: event U={first_update_id} but last_update_id={self.last_update_id}"
            )

        for price_str, qty_str in event["b"]:
            self._update_side(self.bids, -float(price_str), float(qty_str))
        for price_str, qty_str in event["a"]:
            self._update_side(self.asks, float(price_str), float(qty_str))

        self.last_update_id = final_update_id

    @staticmethod
    def _update_side(side: SortedDict, key: float, qty: float) -> None:
        if qty == 0:
            side.pop(key, None)
        else:
            side[key] = qty

    @property
    def best_bid(self) -> float | None:
        if not self.bids:
            return None
        return -self.bids.peekitem(0)[0]

    @property
    def best_ask(self) -> float | None:
        if not self.asks:
            return None
        return self.asks.peekitem(0)[0]

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    def top_levels(self, n: int) -> tuple[list[float], list[float], list[float], list[float]]:
        """Returns (bid_prices, bid_qtys, ask_prices, ask_qtys) for the best n levels each side."""
        bid_prices = [-key for key in self.bids.keys()[:n]]
        bid_qtys = [self.bids[-price] for price in bid_prices]
        ask_prices = list(self.asks.keys()[:n])
        ask_qtys = [self.asks[price] for price in ask_prices]
        return bid_prices, bid_qtys, ask_prices, ask_qtys
