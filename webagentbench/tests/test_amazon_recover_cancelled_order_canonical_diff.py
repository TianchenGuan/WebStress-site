"""End-to-end tests for amazon_recover_cancelled_order canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_recover_cancelled_order",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _reorder(state, targets):
    state.add_to_cart(targets["product_id"], quantity=1)
    state.place_order(
        shipping_address_id=targets["address_id"],
        payment_method_id=targets["payment_id"],
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _reorder(state, targets)

    task = get_task("amazon_recover_cancelled_order")
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

    task = get_task("amazon_recover_cancelled_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_address_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_to_cart(targets["product_id"], quantity=1)
    wrong_addr = next(a for a in state.addresses if a.id != targets["address_id"])
    state.place_order(
        shipping_address_id=wrong_addr.id,
        payment_method_id=targets["payment_id"],
    )

    task = get_task("amazon_recover_cancelled_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_payment_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_to_cart(targets["product_id"], quantity=1)
    wrong_pm = next(p for p in state.payment_methods if p.id != targets["payment_id"])
    state.place_order(
        shipping_address_id=targets["address_id"],
        payment_method_id=wrong_pm.id,
    )

    task = get_task("amazon_recover_cancelled_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_product_fails():
    _, _, targets, initial, state = _setup_session()

    wrong_pid = next(p.id for p in state.products if p.id != targets["product_id"])
    state.add_to_cart(wrong_pid, quantity=1)
    state.place_order(
        shipping_address_id=targets["address_id"],
        payment_method_id=targets["payment_id"],
    )

    task = get_task("amazon_recover_cancelled_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
