"""End-to-end tests for amazon_precision_cart_rebuild canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


REMOVE_NAMES = {"Cotton Bath Towel Set", "Yoga Strap Set", "Vitamin D3 Supplement"}


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_precision_cart_rebuild",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _correct(state, targets):
    # Remove the 3 specified items
    for item in list(state.cart_items):
        if item.product_name in REMOVE_NAMES:
            state.remove_from_cart(item.id)
    # Change quantities
    for item in state.cart_items:
        if item.product_name == "Wireless Mouse Pro":
            item.quantity = 3
        elif item.product_name == "Glass Food Containers":
            item.quantity = 2
    # Add new products
    state.add_to_cart(targets["new_pid_1"], quantity=1)
    state.add_to_cart(targets["new_pid_2"], quantity=1)
    # Checkout
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    return state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _correct(state, targets)

    task = get_task("amazon_precision_cart_rebuild")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_precision_cart_rebuild")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_mouse_quantity_wrong_fails():
    _, _, targets, initial, state = _setup_session()

    for item in list(state.cart_items):
        if item.product_name in REMOVE_NAMES:
            state.remove_from_cart(item.id)
    # Wrong quantity for mouse
    for item in state.cart_items:
        if item.product_name == "Wireless Mouse Pro":
            item.quantity = 2  # wrong, should be 3
        elif item.product_name == "Glass Food Containers":
            item.quantity = 2
    state.add_to_cart(targets["new_pid_1"], quantity=1)
    state.add_to_cart(targets["new_pid_2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_precision_cart_rebuild")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_kept_removed_items_fails():
    _, _, targets, initial, state = _setup_session()

    # Don't remove removed items
    for item in state.cart_items:
        if item.product_name == "Wireless Mouse Pro":
            item.quantity = 3
        elif item.product_name == "Glass Food Containers":
            item.quantity = 2
    state.add_to_cart(targets["new_pid_1"], quantity=1)
    state.add_to_cart(targets["new_pid_2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_precision_cart_rebuild")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
