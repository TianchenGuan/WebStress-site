"""End-to-end tests for amazon_selective_reorder canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_selective_reorder",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _reorder(state, targets, include_sel2=False):
    state.add_to_cart(targets["product_id_sel1"], quantity=1)
    state.add_to_cart(targets["product_id_sel3"], quantity=1)
    if include_sel2:
        state.add_to_cart(targets["product_id_sel2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.viewed_order_ids.append(targets["order_id_sel1"])


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _reorder(state, targets)

    task = get_task("amazon_selective_reorder")
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

    task = get_task("amazon_selective_reorder")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_reorder_sel2_fails():
    # Including sel2 violates the "only sel1 and sel3" constraint
    _, _, targets, initial, state = _setup_session()
    _reorder(state, targets, include_sel2=True)

    task = get_task("amazon_selective_reorder")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_one_product_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_to_cart(targets["product_id_sel1"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.viewed_order_ids.append(targets["order_id_sel1"])

    task = get_task("amazon_selective_reorder")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
