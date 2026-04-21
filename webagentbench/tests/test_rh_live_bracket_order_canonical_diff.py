"""Tests for rh_live_bracket_order canonical_diff."""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_bracket_order", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="MSFT", side="buy", order_type="limit", quantity=Decimal("5"), limit_price=Decimal("395"))
    state.place_order(symbol="MSFT", side="sell", order_type="stop", quantity=Decimal("5"), stop_price=Decimal("380"))
    state.place_order(symbol="MSFT", side="sell", order_type="limit", quantity=Decimal("5"), limit_price=Decimal("430"))

    task = get_task("rh_live_bracket_order")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_missing_stop_loss_fails():
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="MSFT", side="buy", order_type="limit", quantity=Decimal("5"), limit_price=Decimal("395"))
    state.place_order(symbol="MSFT", side="sell", order_type="limit", quantity=Decimal("5"), limit_price=Decimal("430"))

    task = get_task("rh_live_bracket_order")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "missing stop-loss should fail"
