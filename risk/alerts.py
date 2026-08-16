"""Simple rule-based risk alerts, testable in isolation and callable from anywhere
(a script, a notebook, or an Airflow task)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Alert:
    rule: str
    message: str
    severity: str  # "warning" or "critical"


def check_var_breach(latest_pnl_change: float, current_var: float) -> Alert | None:
    """Fires if the most recent P&L step lost more than the current VaR estimate."""
    loss = -latest_pnl_change
    if loss > current_var:
        return Alert(
            rule="var_breach",
            message=f"Loss {loss:.4f} exceeded VaR estimate {current_var:.4f}",
            severity="warning",
        )
    return None


def check_inventory_limit(current_inventory: float, limit: float) -> Alert | None:
    """Fires if absolute inventory exceeds a risk limit."""
    if abs(current_inventory) > limit:
        return Alert(
            rule="inventory_limit",
            message=f"Inventory {current_inventory:.4f} exceeds limit {limit:.4f}",
            severity="critical",
        )
    return None


def check_toxic_flow(current_vpin_regime: str) -> Alert | None:
    """Fires when VPIN signals informed/toxic order flow right now."""
    if current_vpin_regime == "toxic":
        return Alert(
            rule="toxic_flow",
            message="VPIN regime is TOXIC - consider widening quotes or reducing size",
            severity="warning",
        )
    return None


def run_all_checks(
    latest_pnl_change: float,
    current_var: float,
    current_inventory: float,
    inventory_limit: float,
    current_vpin_regime: str,
) -> list[Alert]:
    checks = [
        check_var_breach(latest_pnl_change, current_var),
        check_inventory_limit(current_inventory, inventory_limit),
        check_toxic_flow(current_vpin_regime),
    ]
    return [alert for alert in checks if alert is not None]
