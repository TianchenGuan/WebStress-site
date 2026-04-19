"""End-to-end tests for amazon_cart_optimization canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_cart_optimization",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _optimize_cart(state, targets):
    # Remove the two items
    for name in (targets["remove_item1"], targets["remove_item2"]):
        rm = next(it for it in state.cart_items if it.product_name == name)
        state.remove_from_cart(rm.id)
    # Update quantities
    upd1 = next(it for it in state.cart_items if it.product_name == targets["qty_item1"])
    state.update_cart_quantity(upd1.id, int(targets["qty1"]))
    upd2 = next(it for it in state.cart_items if it.product_name == targets["qty_item2"])
    state.update_cart_quantity(upd2.id, int(targets["qty2"]))
    # Checkout
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _optimize_cart(state, targets)

    task = get_task("amazon_cart_optimization")
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

    task = get_task("amazon_cart_optimization")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_quantity_fails():
    _, _, targets, initial, state = _setup_session()

    for name in (targets["remove_item1"], targets["remove_item2"]):
        rm = next(it for it in state.cart_items if it.product_name == name)
        state.remove_from_cart(rm.id)
    upd1 = next(it for it in state.cart_items if it.product_name == targets["qty_item1"])
    state.update_cart_quantity(upd1.id, 7)  # wrong
    upd2 = next(it for it in state.cart_items if it.product_name == targets["qty_item2"])
    state.update_cart_quantity(upd2.id, int(targets["qty2"]))
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_cart_optimization")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_did_not_remove_fails():
    _, _, targets, initial, state = _setup_session()

    # Didn't remove the items, just updated quantities and checked out
    upd1 = next(it for it in state.cart_items if it.product_name == targets["qty_item1"])
    state.update_cart_quantity(upd1.id, int(targets["qty1"]))
    upd2 = next(it for it in state.cart_items if it.product_name == targets["qty_item2"])
    state.update_cart_quantity(upd2.id, int(targets["qty2"]))
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_cart_optimization")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
