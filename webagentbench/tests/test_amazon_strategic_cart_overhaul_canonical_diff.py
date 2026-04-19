"""End-to-end tests for amazon_strategic_cart_overhaul canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


EXPENSIVE_NAMES = {"Premium Noise-Cancelling Headphones", "Smart Home Security Camera", "Ergonomic Standing Desk Mat"}


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_strategic_cart_overhaul",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _correct_trajectory(state, targets):
    # Remove expensive items
    for item in list(state.cart_items):
        if item.product_name in EXPENSIVE_NAMES:
            state.remove_from_cart(item.id)
    # Add alternatives
    state.add_to_cart(targets["alt_id_1"], quantity=1)
    state.add_to_cart(targets["alt_id_2"], quantity=1)
    # Checkout
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    return state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _correct_trajectory(state, targets)

    task = get_task("amazon_strategic_cart_overhaul")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_strategic_cart_overhaul")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_kept_expensive_items_fails():
    _, _, targets, initial, state = _setup_session()

    # Add alternatives but don't remove expensive items
    state.add_to_cart(targets["alt_id_1"], quantity=1)
    state.add_to_cart(targets["alt_id_2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_strategic_cart_overhaul")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_alt_product_fails():
    _, _, targets, initial, state = _setup_session()

    for item in list(state.cart_items):
        if item.product_name in EXPENSIVE_NAMES:
            state.remove_from_cart(item.id)
    state.add_to_cart(targets["alt_id_1"], quantity=1)  # missing alt_id_2
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_strategic_cart_overhaul")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
