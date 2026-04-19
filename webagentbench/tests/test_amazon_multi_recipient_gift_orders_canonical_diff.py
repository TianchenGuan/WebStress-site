"""End-to-end tests for amazon_multi_recipient_gift_orders canonical_diff."""

from webagentbench.backend.models.amazon import Address
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_multi_recipient_gift_orders",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _add_addr(state, *, name, street, city, st, zip_code):
    a = Address(
        id=state._next_id("addr"),
        full_name=name,
        street_address=street,
        city=city,
        state=st,
        zip_code=zip_code,
    )
    return state.add_address(a)


def _correct(state, targets):
    jamie = _add_addr(state, name=targets["recip_1_name"], street=targets["recip_1_street"], city=targets["recip_1_city"], st=targets["recip_1_state"], zip_code=targets["recip_1_zip"])
    taylor = _add_addr(state, name=targets["recip_2_name"], street=targets["recip_2_street"], city=targets["recip_2_city"], st=targets["recip_2_state"], zip_code=targets["recip_2_zip"])
    pm = next(p for p in state.payment_methods if p.is_default)

    state.add_to_cart(targets["gift_pid_1"], quantity=1)
    state.place_order(shipping_address_id=jamie.id, payment_method_id=pm.id)

    state.add_to_cart(targets["gift_pid_2"], quantity=1)
    state.place_order(shipping_address_id=taylor.id, payment_method_id=pm.id)

    existing = next(a for a in state.addresses if a.full_name == "Jordan Parker" and a.is_default)
    state.add_to_cart(targets["gift_pid_3"], quantity=1)
    state.place_order(shipping_address_id=existing.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _correct(state, targets)

    task = get_task("amazon_multi_recipient_gift_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_multi_recipient_gift_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_recipient_2_address_fails():
    _, _, targets, initial, state = _setup_session()
    jamie = _add_addr(state, name=targets["recip_1_name"], street=targets["recip_1_street"], city=targets["recip_1_city"], st=targets["recip_1_state"], zip_code=targets["recip_1_zip"])
    pm = next(p for p in state.payment_methods if p.is_default)
    state.add_to_cart(targets["gift_pid_1"], quantity=1)
    state.place_order(shipping_address_id=jamie.id, payment_method_id=pm.id)
    # Ship gift 2 to jamie instead
    state.add_to_cart(targets["gift_pid_2"], quantity=1)
    state.place_order(shipping_address_id=jamie.id, payment_method_id=pm.id)
    existing = next(a for a in state.addresses if a.full_name == "Jordan Parker" and a.is_default)
    state.add_to_cart(targets["gift_pid_3"], quantity=1)
    state.place_order(shipping_address_id=existing.id, payment_method_id=pm.id)

    task = get_task("amazon_multi_recipient_gift_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_gift_3_to_jamie_fails():
    _, _, targets, initial, state = _setup_session()
    jamie = _add_addr(state, name=targets["recip_1_name"], street=targets["recip_1_street"], city=targets["recip_1_city"], st=targets["recip_1_state"], zip_code=targets["recip_1_zip"])
    taylor = _add_addr(state, name=targets["recip_2_name"], street=targets["recip_2_street"], city=targets["recip_2_city"], st=targets["recip_2_state"], zip_code=targets["recip_2_zip"])
    pm = next(p for p in state.payment_methods if p.is_default)
    state.add_to_cart(targets["gift_pid_1"], quantity=1)
    state.place_order(shipping_address_id=jamie.id, payment_method_id=pm.id)
    state.add_to_cart(targets["gift_pid_2"], quantity=1)
    state.place_order(shipping_address_id=taylor.id, payment_method_id=pm.id)
    # Ship gift 3 to jamie instead of existing
    state.add_to_cart(targets["gift_pid_3"], quantity=1)
    state.place_order(shipping_address_id=jamie.id, payment_method_id=pm.id)

    task = get_task("amazon_multi_recipient_gift_orders")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
