"""End-to-end tests for amazon_multi_destination_orders canonical_diff."""

from webagentbench.backend.models.amazon import Address
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_multi_destination_orders",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _add_new_address(state, targets):
    addr = Address(
        id=state._next_id("addr"),
        full_name=targets["new_name"],
        street_address=targets["new_street"],
        city=targets["new_city"],
        state=targets["new_state"],
        zip_code=targets["new_zip"],
    )
    return state.add_address(addr)


def _correct(state, targets):
    new_addr = _add_new_address(state, targets)
    pm = next(p for p in state.payment_methods if p.is_default)

    # Order 1: ship product 1 to new address
    state.add_to_cart(targets["product_id_dest1"], quantity=1)
    state.place_order(shipping_address_id=new_addr.id, payment_method_id=pm.id)

    # Order 2: ship product 2 to existing address
    old_addr = next(a for a in state.addresses if a.full_name == "Jordan Parker" and a.is_default)
    state.add_to_cart(targets["product_id_dest2"], quantity=1)
    state.place_order(shipping_address_id=old_addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _correct(state, targets)

    task = get_task("amazon_multi_destination_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_multi_destination_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_new_address_fails():
    _, _, targets, initial, state = _setup_session()

    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.add_to_cart(targets["product_id_dest1"], quantity=1)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.add_to_cart(targets["product_id_dest2"], quantity=1)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_multi_destination_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_both_to_new_address_fails():
    _, _, targets, initial, state = _setup_session()
    new_addr = _add_new_address(state, targets)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.add_to_cart(targets["product_id_dest1"], quantity=1)
    state.place_order(shipping_address_id=new_addr.id, payment_method_id=pm.id)
    state.add_to_cart(targets["product_id_dest2"], quantity=1)
    state.place_order(shipping_address_id=new_addr.id, payment_method_id=pm.id)

    task = get_task("amazon_multi_destination_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
