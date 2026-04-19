"""End-to-end tests for amazon_wishlist_portfolio_rebalance canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_wishlist_portfolio_rebalance",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _rebalance_and_buy(state, targets):
    # Add all 6 to wishlist
    for k in ("e_cheap", "e_exp", "h_cheap", "h_exp", "s_cheap", "s_exp"):
        state.add_to_wishlist(targets[k])
    # Remove the 3 expensive ones (one per category)
    state.remove_from_wishlist(targets["e_exp"])
    state.remove_from_wishlist(targets["h_exp"])
    state.remove_from_wishlist(targets["s_exp"])
    # Move cheap to cart and checkout
    state.add_to_cart(targets["e_cheap"], quantity=1)
    state.add_to_cart(targets["h_cheap"], quantity=1)
    state.add_to_cart(targets["s_cheap"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _rebalance_and_buy(state, targets)

    task = get_task("amazon_wishlist_portfolio_rebalance")
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

    task = get_task("amazon_wishlist_portfolio_rebalance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_bought_expensive_fails():
    _, _, targets, initial, state = _setup_session()

    # Buy all 6 instead of selecting cheap ones
    for k in ("e_cheap", "e_exp", "h_cheap", "h_exp", "s_cheap", "s_exp"):
        state.add_to_cart(targets[k], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_wishlist_portfolio_rebalance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_partial_purchase_fails():
    _, _, targets, initial, state = _setup_session()

    # Only 2 of 3 cheap items purchased
    state.add_to_cart(targets["e_cheap"], quantity=1)
    state.add_to_cart(targets["h_cheap"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_wishlist_portfolio_rebalance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
