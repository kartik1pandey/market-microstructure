from risk.alerts import check_inventory_limit, check_toxic_flow, check_var_breach, run_all_checks


def test_var_breach_fires_when_loss_exceeds_var():
    alert = check_var_breach(latest_pnl_change=-10.0, current_var=5.0)
    assert alert is not None
    assert alert.rule == "var_breach"


def test_var_breach_does_not_fire_when_loss_within_var():
    alert = check_var_breach(latest_pnl_change=-2.0, current_var=5.0)
    assert alert is None


def test_var_breach_does_not_fire_on_a_gain():
    alert = check_var_breach(latest_pnl_change=10.0, current_var=5.0)
    assert alert is None


def test_inventory_limit_fires_when_exceeded():
    alert = check_inventory_limit(current_inventory=-15.0, limit=10.0)
    assert alert is not None
    assert alert.rule == "inventory_limit"
    assert alert.severity == "critical"


def test_inventory_limit_does_not_fire_within_limit():
    alert = check_inventory_limit(current_inventory=5.0, limit=10.0)
    assert alert is None


def test_toxic_flow_fires_on_toxic_regime():
    alert = check_toxic_flow("toxic")
    assert alert is not None
    assert alert.rule == "toxic_flow"


def test_toxic_flow_does_not_fire_on_normal_or_elevated():
    assert check_toxic_flow("normal") is None
    assert check_toxic_flow("elevated") is None


def test_run_all_checks_fires_only_the_triggered_rules():
    alerts = run_all_checks(
        latest_pnl_change=-10.0,  # breaches VaR
        current_var=5.0,
        current_inventory=2.0,  # within limit
        inventory_limit=10.0,
        current_vpin_regime="normal",  # not toxic
    )
    assert len(alerts) == 1
    assert alerts[0].rule == "var_breach"


def test_run_all_checks_can_fire_multiple_rules_simultaneously():
    alerts = run_all_checks(
        latest_pnl_change=-10.0,
        current_var=5.0,
        current_inventory=20.0,
        inventory_limit=10.0,
        current_vpin_regime="toxic",
    )
    rules_fired = {a.rule for a in alerts}
    assert rules_fired == {"var_breach", "inventory_limit", "toxic_flow"}
