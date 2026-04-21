"""Tests for rh_live_buy_the_dip canonical_diff."""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_buy_the_dip", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    aapl_price = state.get_stock("AAPL").price
    limit_price = (aapl_price * Decimal("0.95")).quantize(Decimal("0.01"))
    state.place_order(symbol="AAPL", side="buy", order_type="limit", quantity=Decimal("10"), limit_price=limit_price, time_in_force="gtc")

    task = get_task("rh_live_buy_the_dip")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_market_order_fails():
    """Using market order instead of limit order fails."""
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="AAPL", side="buy", order_type="market", quantity=Decimal("10"))

    task = get_task("rh_live_buy_the_dip")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "market order should fail (must be limit+gtc)"
