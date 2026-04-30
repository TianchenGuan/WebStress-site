"""Tests for rh_live_watch_spread canonical_diff."""

from decimal import Decimal

from webagentbench.backend.price_engine import cascade_update
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_watch_spread", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    cascade_update(state, state._price_engine.advance(17), state._price_engine)
    state.place_order(symbol="TSLA", side="buy", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_live_watch_spread")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_wrong_quantity_fails():
    sm, sid, targets, initial, state = _setup()
    cascade_update(state, state._price_engine.advance(17), state._price_engine)
    state.place_order(symbol="TSLA", side="buy", order_type="market", quantity=Decimal("10"))

    task = get_task("rh_live_watch_spread")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "wrong quantity should fail"


def test_buy_before_reversal_fails():
    sm, sid, targets, initial, state = _setup()
    cascade_update(state, state._price_engine.advance(10), state._price_engine)
    state.place_order(symbol="TSLA", side="buy", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_live_watch_spread")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "buying before two rising ticks should fail"
