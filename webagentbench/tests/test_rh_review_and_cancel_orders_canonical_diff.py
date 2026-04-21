"""End-to-end tests for rh_review_and_cancel_orders canonical_diff.

Task: "Find all pending limit buy orders with prices more than 10% below
current market price and cancel them."

Verifies:
  - Correct trajectory (cancel the 2 far-below orders) passes with score 1.0.
  - Cancelling nothing fails.
  - Cancelling all orders (including reasonably-priced) fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_review_and_cancel_orders",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _far_below_orders(state):
    return [
        o for o in state.orders
        if o.order_type == "limit" and o.side == "buy"
        and o.limit_price is not None
        and float(o.limit_price) < float(state.get_stock(o.symbol).price) * 0.90
        and not o.id.startswith("ord_decoy_")
    ]


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    far_below = _far_below_orders(state)
    assert len(far_below) >= 1, "seed must produce at least one far-below order"
    for order in far_below:
        state.cancel_order(order.id)

    task = get_task("rh_review_and_cancel_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_action_fails():
    """Agent cancels nothing — far-below orders remain pending."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("rh_review_and_cancel_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "cancelling nothing should fail — bijection and constraint require far-below orders to be cancelled"
    )


def test_cancel_all_orders_fails():
    """Agent cancels all orders including reasonably-priced ones."""
    sm, sid, targets, initial, state = _setup_session()
    for order in list(state.orders):
        if order.status == "pending" and not order.id.startswith("ord_decoy_"):
            state.cancel_order(order.id)

    task = get_task("rh_review_and_cancel_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "cancelling reasonably-priced orders should fail — constraint prevents over-cancellation"
    )
