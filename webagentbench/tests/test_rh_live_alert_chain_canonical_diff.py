"""Tests for rh_live_alert_chain canonical_diff."""

from decimal import Decimal, ROUND_UP
import random
from pathlib import Path

import yaml

from webagentbench.backend.price_engine import cascade_update
from webagentbench.backend.state import SessionManager
from webagentbench.eval_core import compute_diff, match_diff
from webagentbench.injector.seed import apply_seed_injection
from webagentbench.injector.server import apply_server_injection
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_alert_chain", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _trigger_nvda_alert(state) -> None:
    state.create_price_alert(symbol="NVDA", condition="above", target_price=Decimal("900"))
    cascade_update(state, {"NVDA": Decimal("901.00")}, state._price_engine)


def _cash_inclusive_sell_quantity(state, target_pct: Decimal = Decimal("50")) -> Decimal:
    total_account_value = state.total_position_value() + state.cash_balance
    current_tech_value = state.sector_value("Technology")
    excess_tech_value = current_tech_value - (total_account_value * target_pct / Decimal("100"))
    if excess_tech_value <= Decimal("0"):
        return Decimal("0")
    return (excess_tech_value / state.get_stock("NVDA").price).quantize(
        Decimal("0.000001"),
        rounding=ROUND_UP,
    )


def _apply_intervention_variant(state) -> None:
    variant_path = Path("webagentbench/injector/variants/rh_live_alert_chain__state_tracking_v1.yaml")
    variant = yaml.safe_load(variant_path.read_text())
    rng = random.Random(42)
    for injection in variant["injections"]:
        if injection["layer"] == "seed":
            apply_seed_injection(state, injection.get("params", {}), rng=rng)
        elif injection["layer"] == "server":
            apply_server_injection(state, injection.get("params", {}))


def test_correct_sell_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    assert initial.sector_pct("Technology") > Decimal("60")

    _trigger_nvda_alert(state)
    state.place_order(
        symbol="NVDA",
        side="sell",
        order_type="market",
        quantity=_cash_inclusive_sell_quantity(state),
    )

    task = get_task("rh_live_alert_chain")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_buy_branch_fails_for_sell_seed():
    sm, sid, targets, initial, state = _setup()
    _trigger_nvda_alert(state)
    state.place_order(symbol="NVDA", side="buy", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_live_alert_chain")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "buying should fail when Technology concentration requires selling NVDA"


def test_missing_sell_fails():
    sm, sid, targets, initial, state = _setup()
    _trigger_nvda_alert(state)

    task = get_task("rh_live_alert_chain")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "missing sell should fail"


def test_intervention_sell_with_duplicate_decoys_passes():
    sm, sid, targets, _initial, state = _setup()
    _apply_intervention_variant(state)
    initial = state.model_copy(deep=True)

    _trigger_nvda_alert(state)
    state.place_order(symbol="NVDA", side="sell", order_type="market", quantity=Decimal("60"))

    task = get_task("rh_live_alert_chain")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
