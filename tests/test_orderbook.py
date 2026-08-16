import pytest

from ingestion.binance.orderbook import OrderBook, SequenceGapError


def make_snapshot(last_update_id=100):
    return {
        "lastUpdateId": last_update_id,
        "bids": [["100.00", "1.5"], ["99.50", "2.0"]],
        "asks": [["100.50", "1.0"], ["101.00", "3.0"]],
    }


def test_apply_snapshot_sets_best_bid_and_ask():
    book = OrderBook(symbol="BTCUSDT")
    book.apply_snapshot(make_snapshot())

    assert book.best_bid == 100.00
    assert book.best_ask == 100.50
    assert book.best_bid < book.best_ask


def test_apply_diff_updates_levels_and_keeps_bid_below_ask():
    book = OrderBook(symbol="BTCUSDT")
    book.apply_snapshot(make_snapshot(last_update_id=100))

    event = {
        "U": 101,
        "u": 102,
        "b": [["100.25", "5.0"]],  # new better bid
        "a": [["100.50", "0"]],  # remove best ask level
    }
    book.apply_diff(event)

    assert book.best_bid == 100.25
    assert book.best_ask == 101.00
    assert book.best_bid < book.best_ask
    assert book.last_update_id == 102


def test_stale_event_is_ignored():
    book = OrderBook(symbol="BTCUSDT")
    book.apply_snapshot(make_snapshot(last_update_id=100))

    stale_event = {"U": 50, "u": 90, "b": [["1.00", "1.0"]], "a": []}
    book.apply_diff(stale_event)

    assert book.last_update_id == 100
    assert -1.00 not in book.bids


def test_sequence_gap_raises():
    book = OrderBook(symbol="BTCUSDT")
    book.apply_snapshot(make_snapshot(last_update_id=100))

    gapped_event = {"U": 105, "u": 110, "b": [], "a": []}  # skips 101-104
    with pytest.raises(SequenceGapError):
        book.apply_diff(gapped_event)


def test_diff_before_snapshot_raises():
    book = OrderBook(symbol="BTCUSDT")
    event = {"U": 1, "u": 2, "b": [], "a": []}
    with pytest.raises(SequenceGapError):
        book.apply_diff(event)


def test_top_levels_returns_best_n_each_side_in_price_priority_order():
    book = OrderBook(symbol="BTCUSDT")
    book.apply_snapshot(make_snapshot())  # bids: 100.00, 99.50 / asks: 100.50, 101.00

    bid_prices, bid_qtys, ask_prices, ask_qtys = book.top_levels(1)

    assert bid_prices == [100.00]
    assert bid_qtys == [1.5]
    assert ask_prices == [100.50]
    assert ask_qtys == [1.0]
