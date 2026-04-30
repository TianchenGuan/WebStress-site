"""Tests for rh_live_buy_the_dip canonical_diff.

Task: Place a GTC limit buy of 10 AAPL at $180 or below, then wait for it to fill.

The canonical_diff requires the order to actually fill (status=filled,
filled_quantity=10) plus the auto-emitted position/transaction/notification.
A pending limit order alone is not sufficient.
"""

from decimal import Decimal

from webagentbench.backend.price_engine import cascade_update
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_buy_the_dip", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _drive_fill(state) -> None:
    """Drop AAPL price below $180 and apply cascade_update to fill any open limit buys."""
    cascade_update(state, {"AAPL": Decimal("178.50")}, state._price_engine)


def test_correct_trajectory_passes():
    """Place limit order at $180, drive price below limit → order fills → eval passes."""
    sm, sid, targets, initial, state = _setup()
    state.place_order(
        symbol="AAPL", side="buy", order_type="limit",
        quantity=Decimal("10"), limit_price=Decimal("180"), time_in_force="gtc",
    )
    _drive_fill(state)

    task = get_task("rh_live_buy_the_dip")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_pending_order_fails():
    """Placing the order without waiting for fill must fail — patience primitive."""
    sm, sid, targets, initial, state = _setup()
    state.place_order(
        symbol="AAPL", side="buy", order_type="limit",
        quantity=Decimal("10"), limit_price=Decimal("180"), time_in_force="gtc",
    )

    task = get_task("rh_live_buy_the_dip")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False, "pending order without fill should fail (patience primitive)"


def test_market_order_fails():
    """Using market order instead of limit fails (instruction requires limit GTC)."""
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="AAPL", side="buy", order_type="market", quantity=Decimal("10"))

    task = get_task("rh_live_buy_the_dip")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False, "market order should fail (must be limit+gtc)"


def test_limit_too_high_fails():
    """Limit price above $180 violates the instruction's threshold."""
    sm, sid, targets, initial, state = _setup()
    state.place_order(
        symbol="AAPL", side="buy", order_type="limit",
        quantity=Decimal("10"), limit_price=Decimal("185"), time_in_force="gtc",
    )
    cascade_update(state, {"AAPL": Decimal("184.0")}, state._price_engine)

    task = get_task("rh_live_buy_the_dip")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False, "limit price above $180 should fail"
