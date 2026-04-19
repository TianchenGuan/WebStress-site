"""End-to-end tests for amazon_wishlist_stock_audit canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_wishlist_stock_audit",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_audit(state, targets, include_out_removal=True):
    state.add_to_cart(targets["in1"], quantity=1)
    state.add_to_cart(targets["in2"], quantity=1)
    state.add_to_cart(targets["in3"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    if include_out_removal:
        state.remove_from_wishlist(targets["out1"])
        state.remove_from_wishlist(targets["out2"])
        state.remove_from_wishlist(targets["out3"])


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _do_audit(state, targets)

    task = get_task("amazon_wishlist_stock_audit")
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

    task = get_task("amazon_wishlist_stock_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_did_not_remove_out_of_stock_fails():
    _, _, targets, initial, state = _setup_session()

    _do_audit(state, targets, include_out_removal=False)

    task = get_task("amazon_wishlist_stock_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_partial_order_fails():
    _, _, targets, initial, state = _setup_session()

    # Only 2 of 3 in-stock items purchased
    state.add_to_cart(targets["in1"], quantity=1)
    state.add_to_cart(targets["in2"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    state.remove_from_wishlist(targets["out1"])
    state.remove_from_wishlist(targets["out2"])
    state.remove_from_wishlist(targets["out3"])

    task = get_task("amazon_wishlist_stock_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
