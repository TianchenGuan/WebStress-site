"""End-to-end tests for amazon_category_exploration canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_category_exploration",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _pick_product_from_cat(state, cat: str):
    for p in state.products:
        if p.category == cat and p.in_stock:
            return p
    raise LookupError(f"no product for category {cat}")


def _checkout_3_categories(state, targets):
    p1 = _pick_product_from_cat(state, targets["cat_1"])
    p2 = _pick_product_from_cat(state, targets["cat_2"])
    p3 = _pick_product_from_cat(state, targets["cat_3"])
    state.add_to_cart(p1.id, quantity=1)
    state.add_to_cart(p2.id, quantity=1)
    state.add_to_cart(p3.id, quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    return state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _checkout_3_categories(state, targets)

    task = get_task("amazon_category_exploration")
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

    task = get_task("amazon_category_exploration")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_categories_fails():
    _, _, targets, initial, state = _setup_session()

    # All 3 items from Electronics — wrong category mix
    elec = [p for p in state.products if p.category == "Electronics" and p.in_stock][:3]
    for p in elec:
        state.add_to_cart(p.id, quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_category_exploration")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_too_few_items_fails():
    _, _, targets, initial, state = _setup_session()

    # Only 2 categories
    p1 = _pick_product_from_cat(state, targets["cat_1"])
    p2 = _pick_product_from_cat(state, targets["cat_2"])
    state.add_to_cart(p1.id, quantity=1)
    state.add_to_cart(p2.id, quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_category_exploration")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
