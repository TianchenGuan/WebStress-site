"""Tests for rh_live_alert_chain canonical_diff."""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_alert_chain", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    state.create_price_alert(symbol="NVDA", condition="above", target_price=Decimal("900"))
    state.place_order(symbol="NVDA", side="buy", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_live_alert_chain")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_missing_buy_fails():
    sm, sid, targets, initial, state = _setup()
    state.create_price_alert(symbol="NVDA", condition="above", target_price=Decimal("900"))

    task = get_task("rh_live_alert_chain")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "missing buy should fail"
