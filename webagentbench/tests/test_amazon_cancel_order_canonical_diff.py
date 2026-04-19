"""End-to-end tests for amazon_cancel_order canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_cancel_order",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _checkout(state, targets, cancel=True):
    state.add_to_cart(targets["product_id"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    order = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    if cancel:
        state.cancel_order(order.id)
    return order


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _checkout(state, targets, cancel=True)

    task = get_task("amazon_cancel_order")
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

    task = get_task("amazon_cancel_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_order_not_cancelled_fails():
    _, _, targets, initial, state = _setup_session()

    _checkout(state, targets, cancel=False)

    task = get_task("amazon_cancel_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_product_fails():
    _, _, targets, initial, state = _setup_session()

    wrong = next(p.id for p in state.products if p.id != targets["product_id"])
    state.add_to_cart(wrong, quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    order = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.cancel_order(order.id)

    task = get_task("amazon_cancel_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
