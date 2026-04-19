"""End-to-end tests for amazon_competitor_switchover canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_competitor_switchover",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _buy(state, targets, pid):
    state.add_to_cart(pid, quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _buy(state, targets, targets["best_pid"])

    task = get_task("amazon_competitor_switchover")
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

    task = get_task("amazon_competitor_switchover")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_bought_reference_product_fails():
    _, _, targets, initial, state = _setup_session()
    _buy(state, targets, targets["ref_pid"])

    task = get_task("amazon_competitor_switchover")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_extra_items_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_to_cart(targets["best_pid"], quantity=1)
    state.add_to_cart(targets["ref_pid"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_competitor_switchover")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
