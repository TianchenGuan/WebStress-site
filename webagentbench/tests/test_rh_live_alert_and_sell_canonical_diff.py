"""Tests for rh_live_alert_and_sell canonical_diff."""

from decimal import Decimal

from webagentbench.backend.price_engine import cascade_update
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_alert_and_sell", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    state.create_price_alert(symbol="TSLA", condition="above", target_price=Decimal("270"))
    cascade_update(state, {"TSLA": Decimal("271.00")}, state._price_engine)
    pos = state.get_position("TSLA")
    if pos:
        state.place_order(symbol="TSLA", side="sell", order_type="market", quantity=pos.quantity)

    task = get_task("rh_live_alert_and_sell")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_missing_sell_fails():
    sm, sid, targets, initial, state = _setup()
    state.create_price_alert(symbol="TSLA", condition="above", target_price=Decimal("270"))
    cascade_update(state, {"TSLA": Decimal("271.00")}, state._price_engine)

    task = get_task("rh_live_alert_and_sell")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "missing sell should fail"
