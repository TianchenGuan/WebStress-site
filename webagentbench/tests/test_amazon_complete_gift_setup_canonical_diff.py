"""End-to-end tests for amazon_complete_gift_setup canonical_diff."""

from webagentbench.backend.models.amazon import Address, PaymentMethod
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_complete_gift_setup",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _add_addr(state, targets):
    addr = Address(
        id=state._next_id("addr"),
        full_name=targets["recipient_name"],
        street_address=targets["street"],
        city=targets["city"],
        state=targets["state_code"],
        zip_code=targets["zip"],
        is_default=False,
    )
    return state.add_address(addr)


def _add_pm(state):
    pm = PaymentMethod(
        id=state._next_id("pm"),
        card_type="Visa",
        last_four="9999",
        expiry="12/28",
        holder_name="Jordan Parker",
        is_default=False,
    )
    return state.add_payment_method(pm)


def _complete(state, targets):
    addr = _add_addr(state, targets)
    pm = _add_pm(state)
    state.add_to_cart(targets["gift_product_id"], quantity=1)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets)

    task = get_task("amazon_complete_gift_setup")
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

    task = get_task("amazon_complete_gift_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_use_existing_payment_fails():
    _, _, targets, initial, state = _setup_session()

    addr = _add_addr(state, targets)
    state.add_to_cart(targets["gift_product_id"], quantity=1)
    existing_pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=existing_pm.id)

    task = get_task("amazon_complete_gift_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_ship_to_existing_address_fails():
    _, _, targets, initial, state = _setup_session()

    pm = _add_pm(state)
    state.add_to_cart(targets["gift_product_id"], quantity=1)
    existing_addr = next(a for a in state.addresses if a.is_default)
    state.place_order(shipping_address_id=existing_addr.id, payment_method_id=pm.id)

    task = get_task("amazon_complete_gift_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
