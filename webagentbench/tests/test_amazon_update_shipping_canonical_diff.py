"""End-to-end tests for amazon_update_shipping canonical_diff."""

from webagentbench.backend.models.amazon import Address
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_update_shipping",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _add_default_addr(state, targets):
    addr = Address(
        id=state._next_id("addr"),
        full_name=targets["recipient_name"],
        street_address=targets["street"],
        city=targets["city"],
        state=targets["state_code"],
        zip_code=targets["zip"],
        is_default=True,
    )
    return state.add_address(addr)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    addr = _add_default_addr(state, targets)
    state.add_to_cart(targets["product_id"], quantity=1)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_update_shipping")
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

    task = get_task("amazon_update_shipping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_order_with_old_address_fails():
    _, _, targets, initial, state = _setup_session()

    _add_default_addr(state, targets)
    state.add_to_cart(targets["product_id"], quantity=1)
    old_addr = next(a for a in state.addresses if a.full_name == "Jordan Parker" and a.is_default is False or a.full_name == "Alex Parker")
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=old_addr.id, payment_method_id=pm.id)

    task = get_task("amazon_update_shipping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_address_not_default_fails():
    _, _, targets, initial, state = _setup_session()

    addr = Address(
        id=state._next_id("addr"),
        full_name=targets["recipient_name"],
        street_address=targets["street"],
        city=targets["city"],
        state=targets["state_code"],
        zip_code=targets["zip"],
        is_default=False,
    )
    state.addresses.append(addr)
    state.add_to_cart(targets["product_id"], quantity=1)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_update_shipping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
