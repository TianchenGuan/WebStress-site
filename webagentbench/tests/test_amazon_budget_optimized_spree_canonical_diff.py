"""End-to-end tests for amazon_budget_optimized_spree canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_budget_optimized_spree",
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
    winners = [targets[f"product_id_cat{i}"] for i in range(1, 6)]
    _checkout(state, winners)

    task = get_task("amazon_budget_optimized_spree")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_budget_optimized_spree")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_category_winner_fails():
    _, _, targets, initial, state = _setup_session()
    winners = [targets[f"product_id_cat{i}"] for i in range(1, 5)]  # missing cat5
    _checkout(state, winners)

    task = get_task("amazon_budget_optimized_spree")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_included_expensive_fails():
    _, _, targets, initial, state = _setup_session()
    winners = [targets[f"product_id_cat{i}"] for i in range(1, 6)]
    expensive = next((p.id for p in state.products if p.in_stock and p.price > 60), None)
    if expensive is None:
        import pytest
        pytest.skip("no expensive product in seed")
    winners.append(expensive)
    _checkout(state, winners)

    task = get_task("amazon_budget_optimized_spree")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
