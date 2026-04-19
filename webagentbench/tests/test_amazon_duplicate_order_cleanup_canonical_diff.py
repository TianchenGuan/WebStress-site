"""End-to-end tests for amazon_duplicate_order_cleanup canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_duplicate_order_cleanup",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    state.cancel_order(targets["newer_order_id"])

    task = get_task("amazon_duplicate_order_cleanup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_duplicate_order_cleanup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_cancel_older_instead_of_newer_fails():
    _, _, targets, initial, state = _setup_session()

    # Agent cancels the WRONG one — the older order
    state.cancel_order(targets["older_order_id"])

    task = get_task("amazon_duplicate_order_cleanup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_cancel_both_orders_fails():
    _, _, targets, initial, state = _setup_session()

    # Agent cancels both — violates the "leave the older one intact" requirement
    state.cancel_order(targets["newer_order_id"])
    state.cancel_order(targets["older_order_id"])

    task = get_task("amazon_duplicate_order_cleanup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_cancel_unrelated_order_fails():
    _, _, targets, initial, state = _setup_session()

    # Agent correctly cancels the newer duplicate, but ALSO cancels a background order
    state.cancel_order(targets["newer_order_id"])
    other_cancellable = next(
        o.id for o in state.orders
        if o.status == "confirmed" and o.id not in (targets["newer_order_id"], targets["older_order_id"])
    )
    state.cancel_order(other_cancellable)

    task = get_task("amazon_duplicate_order_cleanup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
