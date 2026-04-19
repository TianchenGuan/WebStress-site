"""End-to-end tests for amazon_review_aggregation canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.amazon import Review
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_review_aggregation",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _make_review(state, product_id: str, rating: int, title: str, body: str) -> Review:
    return Review(
        id=state._next_id("review"),
        product_id=product_id,
        author_name=state.owner_name,
        rating=rating,
        title=title,
        body=body,
        created_at=datetime.now(timezone.utc),
    )


def _add_all_reviews(state, targets):
    state.add_review(_make_review(
        state, targets["product1_id"], 5, targets["product1_title"],
        "Absolutely love this speaker, the sound quality is exceptional.",
    ))
    state.add_review(_make_review(
        state, targets["product2_id"], 3, targets["product2_title"],
        "These pots work well but one had a small crack on arrival.",
    ))
    state.add_review(_make_review(
        state, targets["product3_id"], 4, targets["product3_title"],
        "Good running shoes, comfortable fit for long distance runs.",
    ))


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _add_all_reviews(state, targets)

    task = get_task("amazon_review_aggregation")
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

    task = get_task("amazon_review_aggregation")
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

    # Product 1 should be 5 stars, we post 4
    state.add_review(_make_review(
        state, targets["product1_id"], 4, targets["product1_title"],
        "Absolutely love this speaker, the sound quality is exceptional.",
    ))
    state.add_review(_make_review(
        state, targets["product2_id"], 3, targets["product2_title"],
        "These pots work well but one had a small crack on arrival.",
    ))
    state.add_review(_make_review(
        state, targets["product3_id"], 4, targets["product3_title"],
        "Good running shoes, comfortable fit for long distance runs.",
    ))

    task = get_task("amazon_review_aggregation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_title_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_review(_make_review(
        state, targets["product1_id"], 5, "Some Other Title",
        "Absolutely love this speaker, the sound quality is exceptional.",
    ))
    state.add_review(_make_review(
        state, targets["product2_id"], 3, targets["product2_title"],
        "These pots work well but one had a small crack on arrival.",
    ))
    state.add_review(_make_review(
        state, targets["product3_id"], 4, targets["product3_title"],
        "Good running shoes, comfortable fit for long distance runs.",
    ))

    task = get_task("amazon_review_aggregation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_only_two_reviews_fails():
    _, _, targets, initial, state = _setup_session()

    # Only 2 reviews
    state.add_review(_make_review(
        state, targets["product1_id"], 5, targets["product1_title"],
        "Absolutely love this speaker, the sound quality is exceptional.",
    ))
    state.add_review(_make_review(
        state, targets["product2_id"], 3, targets["product2_title"],
        "These pots work well but one had a small crack on arrival.",
    ))

    task = get_task("amazon_review_aggregation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
