"""Avellaneda & Stoikov (2008), "High-frequency trading in a limit order book."

Reservation price shifts away from mid-price as inventory builds (more inventory -> more
aggressive skew to offload it); optimal spread widens under higher volatility and further
from the trading horizon.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Quotes:
    bid: float
    ask: float
    reservation_price: float
    spread: float


def reservation_price(
    mid_price: float, inventory: float, gamma: float, sigma: float, time_remaining: float
) -> float:
    """r(s,t,q) = s - q*gamma*sigma^2*(T-t)"""
    return mid_price - inventory * gamma * (sigma**2) * time_remaining


def optimal_spread(gamma: float, sigma: float, time_remaining: float, kappa: float) -> float:
    """total optimal spread = gamma*sigma^2*(T-t) + (2/gamma)*ln(1 + gamma/kappa)"""
    return gamma * (sigma**2) * time_remaining + (2 / gamma) * math.log(1 + gamma / kappa)


def compute_quotes(
    mid_price: float,
    inventory: float,
    gamma: float,
    sigma: float,
    time_remaining: float,
    kappa: float,
) -> Quotes:
    r = reservation_price(mid_price, inventory, gamma, sigma, time_remaining)
    spread = optimal_spread(gamma, sigma, time_remaining, kappa)
    return Quotes(bid=r - spread / 2, ask=r + spread / 2, reservation_price=r, spread=spread)
