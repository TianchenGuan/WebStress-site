"""End-to-end tests for amazon_return_and_rebuy canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_return_and_rebuy",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _complete(state, targets):
    state.request_return(
        order_id=targets["original_order_id"], order_item_index=0, reason="wrong_item",
    )
    state.add_to_cart(targets["replacement_id"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == targets["shipping_name"] and a.street_address == targets["shipping_street"])
    pm = next(p for p in state.payment_methods if p.card_type == targets["payment_type"] and p.last_four == targets["payment_last_four"])
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _complete(state, targets)

    task = get_task("amazon_return_and_rebuy")
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

    task = get_task("amazon_return_and_rebuy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_reason_fails():
    _, _, targets, initial, state = _setup_session()
    state.request_return(
        order_id=targets["original_order_id"], order_item_index=0, reason="defective",
    )
    state.add_to_cart(targets["replacement_id"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == targets["shipping_name"] and a.street_address == targets["shipping_street"])
    pm = next(p for p in state.payment_methods if p.card_type == targets["payment_type"] and p.last_four == targets["payment_last_four"])
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_return_and_rebuy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_rebuy_fails():
    _, _, targets, initial, state = _setup_session()
    state.request_return(
        order_id=targets["original_order_id"], order_item_index=0, reason="wrong_item",
    )

    task = get_task("amazon_return_and_rebuy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_rebought_returned_item_fails():
    _, _, targets, initial, state = _setup_session()
    state.request_return(
        order_id=targets["original_order_id"], order_item_index=0, reason="wrong_item",
    )
    # Rebuy the returned item rather than the replacement
    state.add_to_cart(targets["return_product_id"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == targets["shipping_name"] and a.street_address == targets["shipping_street"])
    pm = next(p for p in state.payment_methods if p.card_type == targets["payment_type"] and p.last_four == targets["payment_last_four"])
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_return_and_rebuy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
