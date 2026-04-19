"""End-to-end tests for amazon_negative_review_return_cascade canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_negative_review_return_cascade",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _file_all_returns(state, targets, reason: str = "Quality below expectations"):
    for pid, oid in zip(
        targets["negative_reviewed_product_ids"],
        targets["order_ids_for_returns"],
        strict=True,
    ):
        order = state.get_order(oid)
        idx = next(
            i for i, it in enumerate(order.items) if it.product_id == pid
        )
        state.request_return(order_id=oid, order_item_index=idx, reason=reason)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _file_all_returns(state, targets)

    task = get_task("amazon_negative_review_return_cascade")
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

    task = get_task("amazon_negative_review_return_cascade")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_only_one_return_filed_fails():
    _, _, targets, initial, state = _setup_session()
    pid = targets["negative_reviewed_product_ids"][0]
    oid = targets["order_ids_for_returns"][0]
    order = state.get_order(oid)
    idx = next(i for i, it in enumerate(order.items) if it.product_id == pid)
    state.request_return(order_id=oid, order_item_index=idx, reason="Quality below expectations")

    task = get_task("amazon_negative_review_return_cascade")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_reason_fails():
    _, _, targets, initial, state = _setup_session()
    _file_all_returns(state, targets, reason="no_longer_needed")

    task = get_task("amazon_negative_review_return_cascade")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_return_on_positive_reviewed_fails():
    """Filing an extra return on a positively-reviewed product should violate invariant."""
    _, _, targets, initial, state = _setup_session()
    _file_all_returns(state, targets)
    # Add an extra return for a positively-reviewed product (rating 5).
    pos_pid = targets["positive_product_id"][0]
    pos_order = next(
        o for o in state.orders
        if any(it.product_id == pos_pid for it in o.items)
    )
    idx = next(i for i, it in enumerate(pos_order.items) if it.product_id == pos_pid)
    state.request_return(
        order_id=pos_order.id, order_item_index=idx, reason="Quality below expectations"
    )

    task = get_task("amazon_negative_review_return_cascade")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
