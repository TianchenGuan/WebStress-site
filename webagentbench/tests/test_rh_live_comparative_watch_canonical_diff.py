"""Tests for rh_live_comparative_watch canonical_diff."""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_comparative_watch", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="MSFT", side="sell", order_type="market", quantity=Decimal("5"))
    state.place_order(symbol="AAPL", side="buy", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_live_comparative_watch")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_missing_aapl_buy_fails():
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="MSFT", side="sell", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_live_comparative_watch")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "missing AAPL buy should fail"
