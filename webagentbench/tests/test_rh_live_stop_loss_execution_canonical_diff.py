"""Tests for rh_live_stop_loss_execution canonical_diff.

Task: Set a stop-loss order at 8% below current NVDA price for 5 shares
(the agent's full position). Wait for the price to drop and trigger the stop.

The canonical_diff requires the stop to actually fire (status=filled,
filled_quantity=5) plus the auto-emitted sell transaction, order-fill
notification, and NVDA position liquidation. A pending stop alone is not
sufficient — that would be just placing protection, not the protection
actually firing.
"""

from decimal import Decimal

from webagentbench.backend.price_engine import cascade_update
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood", task_id="rh_live_stop_loss_execution", seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _drive_stop_trigger(state) -> None:
    """Drop NVDA below the stop threshold and apply cascade_update."""
    cascade_update(state, {"NVDA": Decimal("780.00")}, state._price_engine)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    nvda_price = state.get_stock("NVDA").price
    stop_price = (nvda_price * Decimal("0.92")).quantize(Decimal("0.01"))
    state.place_order(symbol="NVDA", side="sell", order_type="stop",
                      quantity=Decimal("5"), stop_price=stop_price)
    _drive_stop_trigger(state)

    task = get_task("rh_live_stop_loss_execution")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_pending_stop_fails():
    """Stop placed but never triggered — patience/state-tracking violated."""
    sm, sid, targets, initial, state = _setup()
    nvda_price = state.get_stock("NVDA").price
    stop_price = (nvda_price * Decimal("0.92")).quantize(Decimal("0.01"))
    state.place_order(symbol="NVDA", side="sell", order_type="stop",
                      quantity=Decimal("5"), stop_price=stop_price)

    task = get_task("rh_live_stop_loss_execution")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False, "pending stop without trigger should fail"


def test_wrong_order_type_fails():
    """Market sell instead of stop — wrong order type."""
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="NVDA", side="sell", order_type="market",
                      quantity=Decimal("5"))

    task = get_task("rh_live_stop_loss_execution")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False, "market order instead of stop should fail"
