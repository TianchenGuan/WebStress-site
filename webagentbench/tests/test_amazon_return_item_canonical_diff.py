"""End-to-end tests for amazon_return_item canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_return_item",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    state.request_return(order_id=targets["order_id"], order_item_index=0, reason="defective")

    task = get_task("amazon_return_item")
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

    task = get_task("amazon_return_item")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_reason_fails():
    _, _, targets, initial, state = _setup_session()
    state.request_return(order_id=targets["order_id"], order_item_index=0, reason="changed_mind")

    task = get_task("amazon_return_item")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_order_fails():
    _, _, targets, initial, state = _setup_session()

    # Find a delivered order that isn't the target
    wrong_order = next(
        o for o in state.orders
        if o.id != targets["order_id"] and o.status == "delivered"
    )
    state.request_return(order_id=wrong_order.id, order_item_index=0, reason="defective")

    task = get_task("amazon_return_item")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
