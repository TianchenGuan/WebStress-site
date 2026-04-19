"""End-to-end tests for amazon_account_overhaul_and_shop canonical_diff."""

from webagentbench.backend.models.amazon import Address
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_account_overhaul_and_shop",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _complete(state, targets, enable_one_click=True, enable_2fa=True):
    addr1 = Address(
        id=state._next_id("addr"),
        full_name=targets["addr1_name"],
        street_address=targets["addr1_street"],
        city=targets["addr1_city"],
        state=targets["addr1_state"],
        zip_code=targets["addr1_zip"],
        is_default=True,
    )
    state.add_address(addr1)
    addr2 = Address(
        id=state._next_id("addr"),
        full_name=targets["addr2_name"],
        street_address=targets["addr2_street"],
        city=targets["addr2_city"],
        state=targets["addr2_state"],
        zip_code=targets["addr2_zip"],
        is_default=False,
    )
    state.add_address(addr2)

    state.settings.one_click_enabled = enable_one_click
    state.settings.two_factor_enabled = enable_2fa

    state.add_to_cart(targets["product_id_acct1"], quantity=1)
    state.add_to_cart(targets["product_id_acct2"], quantity=1)
    state.add_to_cart(targets["product_id_acct3"], quantity=1)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr1.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets)

    task = get_task("amazon_account_overhaul_and_shop")
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

    task = get_task("amazon_account_overhaul_and_shop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_settings_not_enabled_fails():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets, enable_one_click=False, enable_2fa=False)

    task = get_task("amazon_account_overhaul_and_shop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_default_fails():
    _, _, targets, initial, state = _setup_session()

    # Add Denver as default instead of Austin
    addr2 = Address(
        id=state._next_id("addr"),
        full_name=targets["addr2_name"],
        street_address=targets["addr2_street"],
        city=targets["addr2_city"],
        state=targets["addr2_state"],
        zip_code=targets["addr2_zip"],
        is_default=True,
    )
    state.add_address(addr2)
    addr1 = Address(
        id=state._next_id("addr"),
        full_name=targets["addr1_name"],
        street_address=targets["addr1_street"],
        city=targets["addr1_city"],
        state=targets["addr1_state"],
        zip_code=targets["addr1_zip"],
        is_default=False,
    )
    state.add_address(addr1)

    state.settings.one_click_enabled = True
    state.settings.two_factor_enabled = True

    state.add_to_cart(targets["product_id_acct1"], quantity=1)
    state.add_to_cart(targets["product_id_acct2"], quantity=1)
    state.add_to_cart(targets["product_id_acct3"], quantity=1)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr2.id, payment_method_id=pm.id)

    task = get_task("amazon_account_overhaul_and_shop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_product_fails():
    _, _, targets, initial, state = _setup_session()

    addr1 = Address(
        id=state._next_id("addr"),
        full_name=targets["addr1_name"],
        street_address=targets["addr1_street"],
        city=targets["addr1_city"],
        state=targets["addr1_state"],
        zip_code=targets["addr1_zip"],
        is_default=True,
    )
    state.add_address(addr1)
    addr2 = Address(
        id=state._next_id("addr"),
        full_name=targets["addr2_name"],
        street_address=targets["addr2_street"],
        city=targets["addr2_city"],
        state=targets["addr2_state"],
        zip_code=targets["addr2_zip"],
        is_default=False,
    )
    state.add_address(addr2)

    state.settings.one_click_enabled = True
    state.settings.two_factor_enabled = True

    # Only purchase 2 of 3
    state.add_to_cart(targets["product_id_acct1"], quantity=1)
    state.add_to_cart(targets["product_id_acct2"], quantity=1)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr1.id, payment_method_id=pm.id)

    task = get_task("amazon_account_overhaul_and_shop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
