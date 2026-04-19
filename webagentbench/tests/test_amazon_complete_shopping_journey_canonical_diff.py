"""End-to-end tests for amazon_complete_shopping_journey canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.amazon import Address, Review
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_complete_shopping_journey",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _correct(state, targets):
    # 1. Purchase best speaker
    state.add_to_cart(targets["best_pid"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    # 2. Wishlist cheapest
    state.add_to_wishlist(targets["cheap_pid"])

    # 3. Add 4-star review for past product
    past_product = state.get_product(targets["past_pid"])
    review = Review(
        id=state._next_id("review"),
        product_id=targets["past_pid"],
        author_name=state.owner_name,
        rating=4,
        title=targets["review_title"],
        body="Good product overall",
        created_at=datetime.now(timezone.utc),
    )
    state.reviews.append(review)
    if past_product:
        past_product.review_count += 1

    # 4. Add Casey Jordan address as default
    new_addr = Address(
        id=state._next_id("addr"),
        full_name=targets["addr_name"],
        street_address=targets["addr_street"],
        city=targets["addr_city"],
        state=targets["addr_state"],
        zip_code=targets["addr_zip"],
        is_default=True,
    )
    state.add_address(new_addr)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _correct(state, targets)

    task = get_task("amazon_complete_shopping_journey")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_complete_shopping_journey")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_product_purchased_fails():
    _, _, targets, initial, state = _setup_session()

    # Purchase the mid-rated speaker instead of best
    state.add_to_cart(targets["mid_pid"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.add_to_wishlist(targets["cheap_pid"])
    past_product = state.get_product(targets["past_pid"])
    review = Review(
        id=state._next_id("review"),
        product_id=targets["past_pid"],
        author_name=state.owner_name,
        rating=4,
        title=targets["review_title"],
        body="Good",
        created_at=datetime.now(timezone.utc),
    )
    state.reviews.append(review)
    if past_product:
        past_product.review_count += 1
    new_addr = Address(
        id=state._next_id("addr"),
        full_name=targets["addr_name"],
        street_address=targets["addr_street"],
        city=targets["addr_city"],
        state=targets["addr_state"],
        zip_code=targets["addr_zip"],
        is_default=True,
    )
    state.add_address(new_addr)

    task = get_task("amazon_complete_shopping_journey")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_review_rating_fails():
    _, _, targets, initial, state = _setup_session()
    state.add_to_cart(targets["best_pid"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.add_to_wishlist(targets["cheap_pid"])
    past_product = state.get_product(targets["past_pid"])
    review = Review(
        id=state._next_id("review"),
        product_id=targets["past_pid"],
        author_name=state.owner_name,
        rating=5,  # wrong, should be 4
        title=targets["review_title"],
        body="Good",
        created_at=datetime.now(timezone.utc),
    )
    state.reviews.append(review)
    if past_product:
        past_product.review_count += 1
    new_addr = Address(
        id=state._next_id("addr"),
        full_name=targets["addr_name"],
        street_address=targets["addr_street"],
        city=targets["addr_city"],
        state=targets["addr_state"],
        zip_code=targets["addr_zip"],
        is_default=True,
    )
    state.add_address(new_addr)

    task = get_task("amazon_complete_shopping_journey")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_wishlist_fails():
    _, _, targets, initial, state = _setup_session()
    state.add_to_cart(targets["best_pid"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    # No wishlist
    past_product = state.get_product(targets["past_pid"])
    review = Review(
        id=state._next_id("review"),
        product_id=targets["past_pid"],
        author_name=state.owner_name,
        rating=4,
        title=targets["review_title"],
        body="Good",
        created_at=datetime.now(timezone.utc),
    )
    state.reviews.append(review)
    if past_product:
        past_product.review_count += 1
    new_addr = Address(
        id=state._next_id("addr"),
        full_name=targets["addr_name"],
        street_address=targets["addr_street"],
        city=targets["addr_city"],
        state=targets["addr_state"],
        zip_code=targets["addr_zip"],
        is_default=True,
    )
    state.add_address(new_addr)

    task = get_task("amazon_complete_shopping_journey")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
