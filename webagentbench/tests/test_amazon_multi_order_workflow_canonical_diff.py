"""End-to-end tests for amazon_multi_order_workflow canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_multi_order_workflow",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _checkout_cart(state):
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker" and a.street_address == "742 Evergreen Terrace")
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    return state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def _two_orders(state, targets):
    # Order 1: Electronics
    state.add_to_cart(targets["elec1_id"], quantity=1)
    state.add_to_cart(targets["elec2_id"], quantity=1)
    _checkout_cart(state)
    # Order 2: Books
    state.add_to_cart(targets["book1_id"], quantity=1)
    state.add_to_cart(targets["book2_id"], quantity=1)
    _checkout_cart(state)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _two_orders(state, targets)

    task = get_task("amazon_multi_order_workflow")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_multi_order_workflow")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_one_combined_order_fails():
    _, _, targets, initial, state = _setup_session()

    for pid in [targets["elec1_id"], targets["elec2_id"], targets["book1_id"], targets["book2_id"]]:
        state.add_to_cart(pid, quantity=1)
    _checkout_cart(state)

    task = get_task("amazon_multi_order_workflow")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_book_order_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_to_cart(targets["elec1_id"], quantity=1)
    state.add_to_cart(targets["elec2_id"], quantity=1)
    _checkout_cart(state)

    task = get_task("amazon_multi_order_workflow")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
