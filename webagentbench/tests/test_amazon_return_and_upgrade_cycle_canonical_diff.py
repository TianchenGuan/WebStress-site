"""End-to-end tests for amazon_return_and_upgrade_cycle canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.amazon import Review
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_return_and_upgrade_cycle",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _find_idx(order_items, pid):
    for i, it in enumerate(order_items):
        if it.product_id == pid:
            return i
    return 0


def _complete(state, targets):
    # Returns
    target_order = state.get_order(targets["order_id"])
    i1 = _find_idx(target_order.items, targets["ret_pid_1"])
    state.request_return(order_id=targets["order_id"], order_item_index=i1, reason="defective")
    # Re-fetch to get updated order
    target_order = state.get_order(targets["order_id"])
    i2 = _find_idx(target_order.items, targets["ret_pid_2"])
    state.request_return(order_id=targets["order_id"], order_item_index=i2, reason="not_as_described")

    # Purchase upgrades in one order
    state.add_to_cart(targets["up_pid_1"], quantity=1)
    state.add_to_cart(targets["up_pid_2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    # Review
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["up_pid_1"],
        author_name=state.owner_name,
        rating=5,
        title=targets["review_title"],
        body="Massive improvement over the older model.",
        created_at=datetime.now(timezone.utc),
    ))


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets)

    task = get_task("amazon_return_and_upgrade_cycle")
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

    task = get_task("amazon_return_and_upgrade_cycle")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_return_reasons_fails():
    _, _, targets, initial, state = _setup_session()
    target_order = state.get_order(targets["order_id"])
    i1 = _find_idx(target_order.items, targets["ret_pid_1"])
    state.request_return(order_id=targets["order_id"], order_item_index=i1, reason="not_as_described")
    target_order = state.get_order(targets["order_id"])
    i2 = _find_idx(target_order.items, targets["ret_pid_2"])
    state.request_return(order_id=targets["order_id"], order_item_index=i2, reason="defective")
    state.add_to_cart(targets["up_pid_1"], quantity=1)
    state.add_to_cart(targets["up_pid_2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.add_review(Review(
        id=state._next_id("review"),
        product_id=targets["up_pid_1"],
        author_name=state.owner_name,
        rating=5,
        title=targets["review_title"],
        body="Massive improvement.",
        created_at=datetime.now(timezone.utc),
    ))

    task = get_task("amazon_return_and_upgrade_cycle")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_review_fails():
    _, _, targets, initial, state = _setup_session()
    target_order = state.get_order(targets["order_id"])
    i1 = _find_idx(target_order.items, targets["ret_pid_1"])
    state.request_return(order_id=targets["order_id"], order_item_index=i1, reason="defective")
    target_order = state.get_order(targets["order_id"])
    i2 = _find_idx(target_order.items, targets["ret_pid_2"])
    state.request_return(order_id=targets["order_id"], order_item_index=i2, reason="not_as_described")
    state.add_to_cart(targets["up_pid_1"], quantity=1)
    state.add_to_cart(targets["up_pid_2"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_return_and_upgrade_cycle")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
