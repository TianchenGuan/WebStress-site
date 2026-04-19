"""End-to-end tests for amazon_checkout_with_new_address canonical_diff."""

from webagentbench.backend.models.amazon import Address
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_checkout_with_new_address",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _add_address(state, targets):
    addr = Address(
        id=state._next_id("addr"),
        full_name=targets["recipient_name"],
        street_address=targets["street"],
        city=targets["city"],
        state=targets["state_code"],
        zip_code=targets["zip"],
    )
    return state.add_address(addr)


def _complete(state, targets):
    new_addr = _add_address(state, targets)
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    return state.place_order(shipping_address_id=new_addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets)

    task = get_task("amazon_checkout_with_new_address")
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

    task = get_task("amazon_checkout_with_new_address")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_address_missing_fails():
    _, _, targets, initial, state = _setup_session()

    # Place order with existing address without adding new one
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_checkout_with_new_address")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_address_city_fails():
    _, _, targets, initial, state = _setup_session()

    new_addr = Address(
        id=state._next_id("addr"),
        full_name=targets["recipient_name"],
        street_address=targets["street"],
        city="Dallas",  # WRONG
        state=targets["state_code"],
        zip_code=targets["zip"],
    )
    state.add_address(new_addr)
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    state.place_order(shipping_address_id=new_addr.id, payment_method_id=pm.id)

    task = get_task("amazon_checkout_with_new_address")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_order_uses_old_address_fails():
    _, _, targets, initial, state = _setup_session()

    _add_address(state, targets)  # Add new address
    old_addr = next(a for a in state.addresses if a.is_default)  # Use old default
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    state.place_order(shipping_address_id=old_addr.id, payment_method_id=pm.id)

    task = get_task("amazon_checkout_with_new_address")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
