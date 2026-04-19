"""End-to-end tests for amazon_budget_split_gift_orders canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_budget_split_gift_orders",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _in_category_products(state, category, max_price):
    """Products in the category whose price alone is under max_price."""
    return [p for p in state.products if p.category == category and p.price < max_price]


def _place_order_to(state, product_id, address_id):
    pm = next(p for p in state.payment_methods if p.is_default)
    state.add_to_cart(product_id, quantity=1)
    return state.place_order(shipping_address_id=address_id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    products = _in_category_products(state, targets["category"], targets["per_order_cap"])
    assert len(products) >= 2, "seed must provide >=2 affordable in-category products"

    order_1 = _place_order_to(state, products[0].id, targets["address_1_id"])
    assert order_1.subtotal < targets["per_order_cap"]

    order_2 = _place_order_to(state, products[1].id, targets["address_2_id"])
    assert order_2.subtotal < targets["per_order_cap"]

    task = get_task("amazon_budget_split_gift_orders")
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

    task = get_task("amazon_budget_split_gift_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_single_order_to_one_recipient_fails():
    """Only shipping to Alice, not Bob."""
    _, _, targets, initial, state = _setup_session()

    products = _in_category_products(state, targets["category"], targets["per_order_cap"])
    _place_order_to(state, products[0].id, targets["address_1_id"])

    task = get_task("amazon_budget_split_gift_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_order_exceeds_cap_fails():
    """Place one order whose subtotal equals/exceeds the cap."""
    _, _, targets, initial, state = _setup_session()

    products = _in_category_products(state, targets["category"], targets["per_order_cap"])
    # Order 1: push above cap by stacking 2 products (quantity 2 or 2 items)
    pm = next(p for p in state.payment_methods if p.is_default)
    # Pick a $50+ product and buy two of them to cross the cap.
    expensive = next(p for p in products if p.price >= 50.0)
    state.add_to_cart(expensive.id, quantity=2)  # 2 * $50+ = >$100
    order = state.place_order(shipping_address_id=targets["address_1_id"], payment_method_id=pm.id)
    assert order.subtotal >= targets["per_order_cap"]

    # Order 2 valid
    state.add_to_cart(products[0].id, quantity=1)
    state.place_order(shipping_address_id=targets["address_2_id"], payment_method_id=pm.id)

    task = get_task("amazon_budget_split_gift_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_category_fails():
    """Both orders use products outside Home & Kitchen."""
    _, _, targets, initial, state = _setup_session()

    # Non-H&K products priced under cap, in stock
    off_cat = [
        p for p in state.products
        if p.category != targets["category"]
        and p.price < targets["per_order_cap"]
        and p.in_stock
    ]
    pm = next(p for p in state.payment_methods if p.is_default)
    state.add_to_cart(off_cat[0].id, quantity=1)
    state.place_order(shipping_address_id=targets["address_1_id"], payment_method_id=pm.id)
    state.add_to_cart(off_cat[1].id, quantity=1)
    state.place_order(shipping_address_id=targets["address_2_id"], payment_method_id=pm.id)

    task = get_task("amazon_budget_split_gift_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
