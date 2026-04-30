"""End-to-end tests for amazon_full_account_setup canonical_diff."""

from webagentbench.backend.models.amazon import Address, PaymentMethod
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_full_account_setup",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _complete(state, targets, enable_oc=True, enable_deals=True):
    home = Address(
        id=state._next_id("addr"),
        full_name="Home",
        street_address="200 Pine St",
        city="Seattle",
        state="WA",
        zip_code="98101",
        is_default=False,
    )
    state.add_address(home)
    office = Address(
        id=state._next_id("addr"),
        full_name="Office",
        street_address="800 Corporate Blvd",
        city="Bellevue",
        state="WA",
        zip_code="98004",
        is_default=False,
    )
    state.add_address(office)
    pm = PaymentMethod(
        id=state._next_id("pm"),
        card_type="Visa",
        last_four="9999",
        expiry="12/28",
        holder_name="Jordan Parker",
        is_default=False,
    )
    state.add_payment_method(pm)

    state.settings.one_click_enabled = enable_oc
    state.settings.deal_alerts_email = enable_deals

    state.add_to_cart(targets["product_id"], quantity=1)
    state.place_order(shipping_address_id=office.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets)

    task = get_task("amazon_full_account_setup")
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

    task = get_task("amazon_full_account_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_ship_to_home_fails():
    _, _, targets, initial, state = _setup_session()

    home = Address(
        id=state._next_id("addr"),
        full_name="Home",
        street_address="200 Pine St",
        city="Seattle",
        state="WA",
        zip_code="98101",
        is_default=False,
    )
    state.add_address(home)
    office = Address(
        id=state._next_id("addr"),
        full_name="Office",
        street_address="800 Corporate Blvd",
        city="Bellevue",
        state="WA",
        zip_code="98004",
        is_default=False,
    )
    state.add_address(office)
    pm = PaymentMethod(
        id=state._next_id("pm"),
        card_type="Visa",
        last_four="9999",
        expiry="12/28",
        holder_name="Jordan Parker",
        is_default=False,
    )
    state.add_payment_method(pm)

    state.settings.one_click_enabled = True
    state.settings.deal_alerts_email = True

    state.add_to_cart(targets["product_id"], quantity=1)
    state.place_order(shipping_address_id=home.id, payment_method_id=pm.id)

    task = get_task("amazon_full_account_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_settings_not_enabled_fails():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets, enable_oc=False, enable_deals=False)

    task = get_task("amazon_full_account_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_literal_address_details_fail():
    _, _, targets, initial, state = _setup_session()

    home = Address(
        id=state._next_id("addr"),
        full_name="House",
        street_address="200 Pine St",
        city="Seattle",
        state="WA",
        zip_code="98101",
        is_default=False,
    )
    state.add_address(home)
    office = Address(
        id=state._next_id("addr"),
        full_name="Office",
        street_address="800 Corporate Blvd",
        city="Bellevue",
        state="WA",
        zip_code="98005",
        is_default=False,
    )
    state.add_address(office)
    pm = PaymentMethod(
        id=state._next_id("pm"),
        card_type="Visa",
        last_four="9999",
        expiry="12/28",
        holder_name="Jordan Parker",
        is_default=False,
    )
    state.add_payment_method(pm)
    state.settings.one_click_enabled = True
    state.settings.deal_alerts_email = True
    state.add_to_cart(targets["product_id"], quantity=1)
    state.place_order(shipping_address_id=office.id, payment_method_id=pm.id)

    task = get_task("amazon_full_account_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
