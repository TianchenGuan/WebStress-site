"""End-to-end tests for amazon_cart_budget_limit canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_cart_budget_limit",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _checkout(state, product_ids):
    for pid in product_ids:
        state.add_to_cart(pid, quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker" and a.street_address == "742 Evergreen Terrace")
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    return state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def _three_in_category(state, category, max_total=200):
    chosen = []
    total = 0.0
    for p in state.products:
        if p.category != category or not p.in_stock:
            continue
        if total + p.price > max_total:
            continue
        chosen.append(p.id)
        total += p.price
        if len(chosen) >= 3:
            break
    return chosen


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    chosen = _three_in_category(state, targets["category"])
    _checkout(state, chosen)

    task = get_task("amazon_cart_budget_limit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_cart_budget_limit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_too_few_items_fails():
    _, _, targets, initial, state = _setup_session()
    chosen = _three_in_category(state, targets["category"])[:2]  # only 2 items
    _checkout(state, chosen)

    task = get_task("amazon_cart_budget_limit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_over_budget_fails():
    _, _, targets, initial, state = _setup_session()
    # Pick expensive items totalling over budget
    expensive = [p.id for p in state.products if p.category == targets["category"] and p.in_stock and p.price > 60][:3]
    if not expensive or sum(next(p.price for p in state.products if p.id == pid) for pid in expensive) < float(targets["budget"]):
        import pytest
        pytest.skip("No seed has expensive enough combination")
    _checkout(state, expensive)

    task = get_task("amazon_cart_budget_limit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_category_fails():
    _, _, targets, initial, state = _setup_session()
    other = [p.id for p in state.products if p.category != targets["category"] and p.in_stock][:3]
    _checkout(state, other)

    task = get_task("amazon_cart_budget_limit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
