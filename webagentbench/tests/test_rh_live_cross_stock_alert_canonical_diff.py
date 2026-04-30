"""Tests for rh_live_cross_stock_alert canonical_diff."""

from decimal import Decimal

from webagentbench.backend.price_engine import cascade_update
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_cross_stock_alert", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    state.create_price_alert(symbol="XOM", condition="above", target_price=Decimal("120"))
    state.create_price_alert(symbol="CVX", condition="below", target_price=Decimal("145"))
    cascade_update(state, {"XOM": Decimal("121.00"), "CVX": Decimal("144.00")}, state._price_engine)
    pos_xom = state.get_position("XOM")
    if pos_xom:
        state.place_order(symbol="XOM", side="sell", order_type="market", quantity=pos_xom.quantity)
    state.place_order(symbol="CVX", side="buy", order_type="market", quantity=Decimal("10"))

    task = get_task("rh_live_cross_stock_alert")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_missing_alerts_fails():
    sm, sid, targets, initial, state = _setup()
    pos_xom = state.get_position("XOM")
    if pos_xom:
        state.place_order(symbol="XOM", side="sell", order_type="market", quantity=pos_xom.quantity)
    state.place_order(symbol="CVX", side="buy", order_type="market", quantity=Decimal("10"))

    task = get_task("rh_live_cross_stock_alert")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "missing alerts should fail"
