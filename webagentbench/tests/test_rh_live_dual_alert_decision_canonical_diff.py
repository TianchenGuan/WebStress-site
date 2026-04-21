"""Tests for rh_live_dual_alert_decision canonical_diff."""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_dual_alert_decision", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    state.create_price_alert(symbol="META", condition="above", target_price=Decimal("520"))
    state.create_price_alert(symbol="META", condition="below", target_price=Decimal("480"))
    pos = state.get_position("META")
    if pos:
        state.place_order(symbol="META", side="sell", order_type="market", quantity=pos.quantity)

    task = get_task("rh_live_dual_alert_decision")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_missing_sell_fails():
    sm, sid, targets, initial, state = _setup()
    state.create_price_alert(symbol="META", condition="above", target_price=Decimal("520"))
    state.create_price_alert(symbol="META", condition="below", target_price=Decimal("480"))

    task = get_task("rh_live_dual_alert_decision")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "missing sell should fail"
