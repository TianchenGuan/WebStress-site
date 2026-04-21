"""End-to-end tests for rh_fix_duplicate_orders canonical_diff.

Task: Cancel duplicate pending orders, keeping earliest for each symbol.
AAPL has 3 orders (cancel 2), MSFT and GOOGL have 2 each (cancel 1 each) = 4 cancels.

Verifies:
  - Correct trajectory (cancel 4 duplicates) passes.
  - Under-cancellation (only 2 cancels) fails.
  - Cancelling non-duplicate symbols fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_fix_duplicate_orders",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _get_duplicates(state):
    """Return order_ids that are duplicates (keep first of each symbol, cancel rest)."""
    seen = {}
    to_cancel = []
    non_decoy = [o for o in state.orders if not o.id.startswith("ord_decoy_") and o.status == "pending"]
    non_decoy.sort(key=lambda o: o.created_at)
    for o in non_decoy:
        if o.symbol in seen:
            to_cancel.append(o.id)
        else:
            seen[o.symbol] = o.id
    return to_cancel


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    duplicates = _get_duplicates(state)
    assert len(duplicates) >= 4, f"expected >=4 duplicates, got {len(duplicates)}"

    for oid in duplicates:
        state.cancel_order(oid)

    task = get_task("rh_fix_duplicate_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_under_cancellation_fails():
    """Agent only cancels 2 of the 4 required duplicate orders."""
    sm, sid, targets, initial, state = _setup_session()
    duplicates = _get_duplicates(state)
    assert len(duplicates) >= 4

    for oid in duplicates[:2]:  # only cancel 2 of 4
        state.cancel_order(oid)

    task = get_task("rh_fix_duplicate_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "under-cancellation should fail"


def test_cancelling_non_duplicate_fails():
    """Agent cancels all orders for a symbol that only has one (AMZN)."""
    sm, sid, targets, initial, state = _setup_session()
    duplicates = _get_duplicates(state)

    for oid in duplicates:
        state.cancel_order(oid)

    amzn_orders = [o for o in state.orders if o.symbol == "AMZN" and o.status == "pending"]
    if amzn_orders:
        state.cancel_order(amzn_orders[0].id)  # wrong: cancel the only AMZN order

    task = get_task("rh_fix_duplicate_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "cancelling non-duplicate AMZN order should fail"
