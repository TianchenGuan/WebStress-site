"""End-to-end tests for amazon_compare_and_buy_cheapest canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_compare_and_buy_cheapest",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _checkout(state, targets, product_id, quantity=1):
    state.add_to_cart(product_id, quantity=quantity)
    addr = next(a for a in state.addresses if a.full_name == targets["shipping_name"] and a.street_address == targets["shipping_street"])
    pm = next(p for p in state.payment_methods if p.card_type == targets["payment_type"] and p.last_four == targets["payment_last_four"])
    return state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _checkout(state, targets, targets["cheapest_product_id"])

    task = get_task("amazon_compare_and_buy_cheapest")
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

    task = get_task("amazon_compare_and_buy_cheapest")
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

    wrong = next(p.id for p in state.products if p.id != targets["cheapest_product_id"] and p.in_stock)
    _checkout(state, targets, wrong)

    task = get_task("amazon_compare_and_buy_cheapest")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_with_extra_items_fails():
    _, _, targets, initial, state = _setup_session()

    # Add cheapest plus an extra item — should fail because order must contain only 1 item.
    state.add_to_cart(targets["cheapest_product_id"], quantity=1)
    extra = next(p.id for p in state.products if p.id != targets["cheapest_product_id"] and p.in_stock)
    state.add_to_cart(extra, quantity=1)
    addr = next(a for a in state.addresses if a.full_name == targets["shipping_name"] and a.street_address == targets["shipping_street"])
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_compare_and_buy_cheapest")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_quantity_fails():
    _, _, targets, initial, state = _setup_session()

    _checkout(state, targets, targets["cheapest_product_id"], quantity=2)

    task = get_task("amazon_compare_and_buy_cheapest")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
