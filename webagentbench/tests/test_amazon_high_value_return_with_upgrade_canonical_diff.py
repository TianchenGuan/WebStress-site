"""End-to-end tests for amazon_high_value_return_with_upgrade canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_high_value_return_with_upgrade",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _complete(state, targets, return_reason="Upgrading to a better model"):
    state.request_return(
        order_id=targets["old_order_id"],
        order_item_index=0,
        reason=return_reason,
    )
    state.add_to_cart(targets["upgrade_product_id"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets)

    task = get_task("amazon_high_value_return_with_upgrade")
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

    task = get_task("amazon_high_value_return_with_upgrade")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_return_wrong_order_fails():
    """Returning the cheaper order instead of the most expensive."""
    _, _, targets, initial, state = _setup_session()

    # Pick the "order_1" order (the cheap $149 one, not the $299 target)
    wrong_order = next(o for o in state.orders if o.id == "order_1")
    state.request_return(
        order_id=wrong_order.id,
        order_item_index=0,
        reason="Upgrading to a better model",
    )
    state.add_to_cart(targets["upgrade_product_id"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_high_value_return_with_upgrade")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_upgrade_order_fails():
    _, _, targets, initial, state = _setup_session()

    state.request_return(
        order_id=targets["old_order_id"],
        order_item_index=0,
        reason="Upgrading to a better model",
    )

    task = get_task("amazon_high_value_return_with_upgrade")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_return_reason_fails():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets, return_reason="defective")

    task = get_task("amazon_high_value_return_with_upgrade")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
