"""End-to-end tests for rh_cancel_pending_order canonical_diff.

Task: "Cancel the pending limit order for MSFT."

Verifies:
  - Correct trajectory (MSFT limit order cancelled) passes with score 1.0.
  - Wrong order cancelled (AAPL instead of MSFT) fails.
  - Extra cancellation (MSFT + another) fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_cancel_pending_order",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _find_order(state, symbol: str):
    return next(
        (o for o in state.orders if o.symbol == symbol and o.status == "pending"),
        None,
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    msft_order = _find_order(state, "MSFT")
    assert msft_order is not None, "seed must produce a pending MSFT order"
    state.cancel_order(msft_order.id)

    task = get_task("rh_cancel_pending_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_order_cancelled_fails():
    """Agent cancels AAPL instead of MSFT."""
    sm, sid, targets, initial, state = _setup_session()
    aapl_order = _find_order(state, "AAPL")
    assert aapl_order is not None, "seed must produce a pending AAPL order"
    state.cancel_order(aapl_order.id)

    task = get_task("rh_cancel_pending_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "cancelling AAPL instead of MSFT should fail — where clause requires symbol=MSFT"
    )


def test_extra_cancellation_fails():
    """Agent correctly cancels MSFT AND also cancels another order."""
    sm, sid, targets, initial, state = _setup_session()
    msft_order = _find_order(state, "MSFT")
    aapl_order = _find_order(state, "AAPL")
    assert msft_order is not None and aapl_order is not None
    state.cancel_order(msft_order.id)
    state.cancel_order(aapl_order.id)

    task = get_task("rh_cancel_pending_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "cancelling an extra order should violate the non-MSFT orders invariant"
    )
