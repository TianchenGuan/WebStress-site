"""End-to-end tests for amazon_bulk_cart_build canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_bulk_cart_build",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _bulk_cart(state, targets):
    state.add_to_cart(targets["pid_1"], quantity=2)
    state.add_to_cart(targets["pid_2"], quantity=1)
    state.add_to_cart(targets["pid_3"], quantity=3)
    state.add_to_cart(targets["pid_4"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _bulk_cart(state, targets)

    task = get_task("amazon_bulk_cart_build")
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

    task = get_task("amazon_bulk_cart_build")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_quantity_fails():
    _, _, targets, initial, state = _setup_session()

    # Wrong quantity for pid_3 — should be 3, agent uses 1
    state.add_to_cart(targets["pid_1"], quantity=2)
    state.add_to_cart(targets["pid_2"], quantity=1)
    state.add_to_cart(targets["pid_3"], quantity=1)
    state.add_to_cart(targets["pid_4"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_bulk_cart_build")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_product_fails():
    _, _, targets, initial, state = _setup_session()

    # Missing pid_4
    state.add_to_cart(targets["pid_1"], quantity=2)
    state.add_to_cart(targets["pid_2"], quantity=1)
    state.add_to_cart(targets["pid_3"], quantity=3)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_bulk_cart_build")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
