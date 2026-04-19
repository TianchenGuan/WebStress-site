"""End-to-end tests for amazon_cross_category_value_hunt canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_cross_category_value_hunt",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _checkout(state, product_ids):
    for pid in product_ids:
        state.add_to_cart(pid, quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    return state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _checkout(state, [targets["best_id_1"], targets["best_id_2"]])

    task = get_task("amazon_cross_category_value_hunt")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_cross_category_value_hunt")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_included_third_fails():
    _, _, targets, initial, state = _setup_session()
    _checkout(state, [targets["best_id_1"], targets["third_id"]])

    task = get_task("amazon_cross_category_value_hunt")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_only_one_best_fails():
    _, _, targets, initial, state = _setup_session()
    _checkout(state, [targets["best_id_1"]])

    task = get_task("amazon_cross_category_value_hunt")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_three_items_fails():
    _, _, targets, initial, state = _setup_session()
    _checkout(state, [targets["best_id_1"], targets["best_id_2"], targets["third_id"]])

    task = get_task("amazon_cross_category_value_hunt")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
