"""End-to-end tests for amazon_full_order_lifecycle canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.amazon import Review
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_full_order_lifecycle",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _correct(state, targets):
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)

    # 1. Order cancel_pid and cancel
    state.add_to_cart(targets["cancel_pid"], quantity=1)
    o1 = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.cancel_order(o1.id)

    # 2. Order keep_pid + return_pid together
    state.add_to_cart(targets["keep_pid"], quantity=1)
    state.add_to_cart(targets["return_pid"], quantity=1)
    o2 = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    # 3. Return return_pid
    return_idx = next(i for i, it in enumerate(o2.items) if it.product_id == targets["return_pid"])
    state.request_return(order_id=o2.id, order_item_index=return_idx, reason="not_as_described")

    # 4. Review keep_pid with 5 stars
    review = Review(
        id=state._next_id("review"),
        product_id=targets["keep_pid"],
        author_name=state.owner_name,
        rating=5,
        title=targets["review_title"],
        body="Excellent product",
        created_at=datetime.now(timezone.utc),
    )
    state.add_review(review)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _correct(state, targets)

    task = get_task("amazon_full_order_lifecycle")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_full_order_lifecycle")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_cancel_fails():
    _, _, targets, initial, state = _setup_session()
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)

    # Don't cancel first order
    state.add_to_cart(targets["cancel_pid"], quantity=1)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.add_to_cart(targets["keep_pid"], quantity=1)
    state.add_to_cart(targets["return_pid"], quantity=1)
    o2 = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    return_idx = next(i for i, it in enumerate(o2.items) if it.product_id == targets["return_pid"])
    state.request_return(order_id=o2.id, order_item_index=return_idx, reason="not_as_described")
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["keep_pid"],
        author_name=state.owner_name,
        rating=5,
        title=targets["review_title"],
        body="Ok",
        created_at=datetime.now(timezone.utc),
    ))

    task = get_task("amazon_full_order_lifecycle")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_return_fails():
    _, _, targets, initial, state = _setup_session()
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)

    state.add_to_cart(targets["cancel_pid"], quantity=1)
    o1 = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.cancel_order(o1.id)
    state.add_to_cart(targets["keep_pid"], quantity=1)
    state.add_to_cart(targets["return_pid"], quantity=1)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    # Don't file return
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["keep_pid"],
        author_name=state.owner_name,
        rating=5,
        title=targets["review_title"],
        body="Ok",
        created_at=datetime.now(timezone.utc),
    ))

    task = get_task("amazon_full_order_lifecycle")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_review_fails():
    _, _, targets, initial, state = _setup_session()
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)

    state.add_to_cart(targets["cancel_pid"], quantity=1)
    o1 = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.cancel_order(o1.id)
    state.add_to_cart(targets["keep_pid"], quantity=1)
    state.add_to_cart(targets["return_pid"], quantity=1)
    o2 = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    return_idx = next(i for i, it in enumerate(o2.items) if it.product_id == targets["return_pid"])
    state.request_return(order_id=o2.id, order_item_index=return_idx, reason="not_as_described")
    # No review

    task = get_task("amazon_full_order_lifecycle")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
