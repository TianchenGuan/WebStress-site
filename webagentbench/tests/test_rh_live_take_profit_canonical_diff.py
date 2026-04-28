"""Tests for rh_live_take_profit canonical_diff.

Task: Set a limit sell on the entire TSLA position (10 shares) at ≥$260,
then wait for the price to rise above $260 so the order fills.

The canonical_diff requires the order to actually fill (status=filled) plus
the auto-emitted sell transaction, order-fill notification, and TSLA
position liquidation. A pending limit order alone is not sufficient.
"""

from decimal import Decimal

from webagentbench.backend.price_engine import cascade_update
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_take_profit", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _drive_fill(state) -> None:
    """Push TSLA above $260 and apply cascade_update to fill the limit sell."""
    cascade_update(state, {"TSLA": Decimal("265.00")}, state._price_engine)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    state.place_order(
        symbol="TSLA", side="sell", order_type="limit",
        quantity=Decimal("10"), limit_price=Decimal("260"),
    )
    _drive_fill(state)

    task = get_task("rh_live_take_profit")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_pending_order_fails():
    """Patience primitive: pending sell without fill must fail."""
    sm, sid, targets, initial, state = _setup()
    state.place_order(
        symbol="TSLA", side="sell", order_type="limit",
        quantity=Decimal("10"), limit_price=Decimal("265"),
    )

    task = get_task("rh_live_take_profit")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False, "pending order without fill should fail"


def test_below_target_price_fails():
    """Limit price below $260 violates the instruction's threshold."""
    sm, sid, targets, initial, state = _setup()
    state.place_order(
        symbol="TSLA", side="sell", order_type="limit",
        quantity=Decimal("10"), limit_price=Decimal("250"),
    )
    cascade_update(state, {"TSLA": Decimal("255.00")}, state._price_engine)

    task = get_task("rh_live_take_profit")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False, "limit price below $260 should fail"
