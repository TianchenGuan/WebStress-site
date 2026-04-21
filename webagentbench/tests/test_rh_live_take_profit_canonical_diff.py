"""Tests for rh_live_take_profit canonical_diff."""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_take_profit", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="TSLA", side="sell", order_type="limit", quantity=Decimal("10"), limit_price=Decimal("265"))

    task = get_task("rh_live_take_profit")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_below_target_price_fails():
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="TSLA", side="sell", order_type="limit", quantity=Decimal("10"), limit_price=Decimal("250"))

    task = get_task("rh_live_take_profit")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "limit price below $260 should fail"
