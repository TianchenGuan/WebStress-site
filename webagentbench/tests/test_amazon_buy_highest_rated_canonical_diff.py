"""End-to-end tests for amazon_buy_highest_rated canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_buy_highest_rated",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _checkout(state, product_id):
    state.add_to_cart(product_id, quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker" and a.street_address == "742 Evergreen Terrace")
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    return state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _checkout(state, targets["best_product_id"])

    task = get_task("amazon_buy_highest_rated")
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

    task = get_task("amazon_buy_highest_rated")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_product_fails():
    _, _, targets, initial, state = _setup_session()

    wrong = next(p.id for p in state.products if p.id != targets["best_product_id"] and p.in_stock)
    _checkout(state, wrong)

    task = get_task("amazon_buy_highest_rated")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_address_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_to_cart(targets["best_product_id"], quantity=1)
    wrong_addr = next(a for a in state.addresses if a.full_name == "Alex Parker")
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    state.place_order(shipping_address_id=wrong_addr.id, payment_method_id=pm.id)

    task = get_task("amazon_buy_highest_rated")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_excess_review_fails():
    _, _, targets, initial, state = _setup_session()

    _checkout(state, targets["best_product_id"])
    from webagentbench.backend.models.amazon import Review
    from datetime import datetime, timezone
    review = Review(
        id=state._next_id("review"),
        product_id=targets["best_product_id"],
        author_name=state.owner_name,
        rating=5,
        title="Great",
        body="Nice",
        created_at=datetime.now(timezone.utc),
    )
    state.reviews.append(review)

    task = get_task("amazon_buy_highest_rated")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
