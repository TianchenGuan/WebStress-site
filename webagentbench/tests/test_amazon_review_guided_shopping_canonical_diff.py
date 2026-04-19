"""End-to-end tests for amazon_review_guided_shopping canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.amazon import Review
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_review_guided_shopping",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _complete(state, targets, include_low_wishlist=True):
    # Buy both best products in a single order
    state.add_to_cart(targets["best1"], quantity=1)
    state.add_to_cart(targets["best2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    # Add 5-star review for best1
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["best1"],
        author_name=state.owner_name,
        rating=5,
        title=targets["review_title_1"],
        body="Absolutely love this product!",
        created_at=datetime.now(timezone.utc),
    ))
    # Add 4-star review for best2
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["best2"],
        author_name=state.owner_name,
        rating=4,
        title=targets["review_title_2"],
        body="Great everyday essential and works as expected.",
        created_at=datetime.now(timezone.utc),
    ))

    if include_low_wishlist:
        state.add_to_wishlist(targets["low1"])
        state.add_to_wishlist(targets["low2"])


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets)

    task = get_task("amazon_review_guided_shopping")
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

    task = get_task("amazon_review_guided_shopping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_missing_reviews_fails():
    _, _, targets, initial, state = _setup_session()

    # Buy both products but skip reviews
    state.add_to_cart(targets["best1"], quantity=1)
    state.add_to_cart(targets["best2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.add_to_wishlist(targets["low1"])
    state.add_to_wishlist(targets["low2"])

    task = get_task("amazon_review_guided_shopping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_wishlist_fails():
    _, _, targets, initial, state = _setup_session()

    _complete(state, targets, include_low_wishlist=False)

    task = get_task("amazon_review_guided_shopping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_review_ratings_fails():
    _, _, targets, initial, state = _setup_session()

    # Correct purchase + wishlist
    state.add_to_cart(targets["best1"], quantity=1)
    state.add_to_cart(targets["best2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.add_to_wishlist(targets["low1"])
    state.add_to_wishlist(targets["low2"])

    # Wrong ratings: swap them
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["best1"],
        author_name=state.owner_name,
        rating=4,  # should be 5
        title=targets["review_title_1"],
        body="Love this product!",
        created_at=datetime.now(timezone.utc),
    ))
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["best2"],
        author_name=state.owner_name,
        rating=5,  # should be 4
        title=targets["review_title_2"],
        body="Great everyday essential.",
        created_at=datetime.now(timezone.utc),
    ))

    task = get_task("amazon_review_guided_shopping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_bought_low_rated_products_fails():
    _, _, targets, initial, state = _setup_session()

    # Buy low-rated products by mistake
    state.add_to_cart(targets["low1"], quantity=1)
    state.add_to_cart(targets["low2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["best1"],
        author_name=state.owner_name,
        rating=5,
        title=targets["review_title_1"],
        body="Love this!",
        created_at=datetime.now(timezone.utc),
    ))
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["best2"],
        author_name=state.owner_name,
        rating=4,
        title=targets["review_title_2"],
        body="Good.",
        created_at=datetime.now(timezone.utc),
    ))
    state.add_to_wishlist(targets["low1"])
    state.add_to_wishlist(targets["low2"])

    task = get_task("amazon_review_guided_shopping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
