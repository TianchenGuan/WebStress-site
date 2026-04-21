"""Tests for rh_live_stop_loss_execution canonical_diff."""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_stop_loss_execution", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    nvda_price = state.get_stock("NVDA").price
    stop_price = (nvda_price * Decimal("0.92")).quantize(Decimal("0.01"))
    state.place_order(symbol="NVDA", side="sell", order_type="stop", quantity=Decimal("5"), stop_price=stop_price)

    task = get_task("rh_live_stop_loss_execution")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_wrong_order_type_fails():
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="NVDA", side="sell", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_live_stop_loss_execution")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "market order instead of stop should fail"
