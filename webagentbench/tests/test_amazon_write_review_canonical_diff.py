"""End-to-end tests for amazon_write_review canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.amazon import Review
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_write_review",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["product_id"],
        author_name=state.owner_name,
        rating=5,
        title="Absolutely love it",
        body="This product is amazing and works perfectly every day.",
        created_at=datetime.now(timezone.utc),
    ))

    task = get_task("amazon_write_review")
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

    task = get_task("amazon_write_review")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_rating_fails():
    _, _, targets, initial, state = _setup_session()
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["product_id"],
        author_name=state.owner_name,
        rating=4,  # should be 5
        title="Absolutely love it",
        body="Great product overall.",
        created_at=datetime.now(timezone.utc),
    ))

    task = get_task("amazon_write_review")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_title_fails():
    _, _, targets, initial, state = _setup_session()
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["product_id"],
        author_name=state.owner_name,
        rating=5,
        title="Nice product",  # wrong title
        body="Great product overall.",
        created_at=datetime.now(timezone.utc),
    ))

    task = get_task("amazon_write_review")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_product_fails():
    _, _, targets, initial, state = _setup_session()
    wrong = next(p.id for p in state.products if p.id != targets["product_id"])
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=wrong,
        author_name=state.owner_name,
        rating=5,
        title="Absolutely love it",
        body="Great product overall.",
        created_at=datetime.now(timezone.utc),
    ))

    task = get_task("amazon_write_review")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
