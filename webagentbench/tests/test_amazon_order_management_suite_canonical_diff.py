"""End-to-end tests for amazon_order_management_suite canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_order_management_suite",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _complete(state, targets, cancel_first=True):
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker" and "742 Evergreen" in a.street_address)
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")

    state.add_to_cart(targets["first_product_id"], quantity=1)
    first = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    if cancel_first:
        state.cancel_order(first.id)

    state.add_to_cart(targets["second_item1_id"], quantity=1)
    state.add_to_cart(targets["second_item2_id"], quantity=1)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets)

    task = get_task("amazon_order_management_suite")
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

    task = get_task("amazon_order_management_suite")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_first_order_not_cancelled_fails():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets, cancel_first=False)

    task = get_task("amazon_order_management_suite")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_second_order_fails():
    _, _, targets, initial, state = _setup_session()

    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker" and "742 Evergreen" in a.street_address)
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")

    state.add_to_cart(targets["first_product_id"], quantity=1)
    first = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.cancel_order(first.id)

    task = get_task("amazon_order_management_suite")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
