import pytest

from alpha.avellaneda_stoikov import compute_quotes, optimal_spread, reservation_price


def test_reservation_price_skews_away_from_inventory():
    base = reservation_price(mid_price=100.0, inventory=0, gamma=0.1, sigma=0.01, time_remaining=1.0)
    long_position = reservation_price(mid_price=100.0, inventory=10, gamma=0.1, sigma=0.01, time_remaining=1.0)
    short_position = reservation_price(mid_price=100.0, inventory=-10, gamma=0.1, sigma=0.01, time_remaining=1.0)

    assert base == 100.0
    assert long_position < base  # long inventory -> skew reservation price down (encourage selling)
    assert short_position > base  # short inventory -> skew up (encourage buying)


def test_spread_increases_monotonically_with_sigma():
    spreads = [
        optimal_spread(gamma=0.1, sigma=s, time_remaining=1.0, kappa=1.5)
        for s in [0.001, 0.005, 0.01, 0.02, 0.05]
    ]
    assert spreads == sorted(spreads)
    assert spreads[0] < spreads[-1]


def test_spread_increases_monotonically_with_gamma():
    # Note: the AS spread formula is gamma*sigma^2*T + (2/gamma)*ln(1+gamma/kappa) - the
    # second term actually *decreases* in gamma, so monotonicity in gamma only holds once
    # the first (linear, inventory-risk) term dominates. sigma=1.0 here puts us in that
    # regime; sigma=0.01 (a tiny per-tick vol) would NOT be monotonic across this same
    # gamma range - this is a real property of the formula, not an arbitrary choice.
    spreads = [
        optimal_spread(gamma=g, sigma=1.0, time_remaining=1.0, kappa=1.5)
        for g in [0.1, 0.5, 1.0, 5.0, 10.0]
    ]
    assert spreads == sorted(spreads)
    assert spreads[0] < spreads[-1]


def test_spread_shrinks_as_time_remaining_approaches_zero():
    far_from_horizon = optimal_spread(gamma=0.1, sigma=0.01, time_remaining=1.0, kappa=1.5)
    near_horizon = optimal_spread(gamma=0.1, sigma=0.01, time_remaining=0.01, kappa=1.5)
    assert near_horizon < far_from_horizon


def test_compute_quotes_brackets_reservation_price():
    quotes = compute_quotes(mid_price=100.0, inventory=2, gamma=0.1, sigma=0.01, time_remaining=1.0, kappa=1.5)
    assert quotes.bid < quotes.reservation_price < quotes.ask
    assert quotes.ask - quotes.bid == pytest.approx(quotes.spread)
