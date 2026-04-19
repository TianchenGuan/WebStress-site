"""End-to-end tests for amazon_delivered_review_chain canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.amazon import Review
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_delivered_review_chain",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _complete(state, targets):
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["review_pid_1"],
        author_name=state.owner_name,
        rating=5,
        title=targets["review_title_1"],
        body="Excellent sound quality and noise isolation.",
        created_at=datetime.now(timezone.utc),
    ))
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["review_pid_2"],
        author_name=state.owner_name,
        rating=3,
        title=targets["review_title_2"],
        body="Gets the job done but nothing special.",
        created_at=datetime.now(timezone.utc),
    ))
    state.add_to_cart(targets["product_id_reorder"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets)

    task = get_task("amazon_delivered_review_chain")
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

    task = get_task("amazon_delivered_review_chain")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_swapped_review_ratings_fails():
    _, _, targets, initial, state = _setup_session()
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["review_pid_1"],
        author_name=state.owner_name,
        rating=3,  # should be 5
        title=targets["review_title_1"],
        body="...",
        created_at=datetime.now(timezone.utc),
    ))
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["review_pid_2"],
        author_name=state.owner_name,
        rating=5,  # should be 3
        title=targets["review_title_2"],
        body="...",
        created_at=datetime.now(timezone.utc),
    ))
    state.add_to_cart(targets["product_id_reorder"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_delivered_review_chain")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_reorder_fails():
    _, _, targets, initial, state = _setup_session()
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["review_pid_1"],
        author_name=state.owner_name,
        rating=5,
        title=targets["review_title_1"],
        body="Great.",
        created_at=datetime.now(timezone.utc),
    ))
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["review_pid_2"],
        author_name=state.owner_name,
        rating=3,
        title=targets["review_title_2"],
        body="OK.",
        created_at=datetime.now(timezone.utc),
    ))

    task = get_task("amazon_delivered_review_chain")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
