"""End-to-end tests for amazon_wishlist_curation canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_wishlist_curation",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _curate_and_buy(state, targets):
    # Add all 5 to wishlist
    for pid_key in ("prod1_id", "prod2_id", "prod3_id", "prod4_id", "prod5_id"):
        state.add_to_wishlist(targets[pid_key])
    # Remove the 2 most expensive (prod1 $199.99, prod3 $249.99)
    state.remove_from_wishlist(targets["prod1_id"])
    state.remove_from_wishlist(targets["prod3_id"])
    # Buy the 3 remaining (prod2, prod4, prod5)
    state.add_to_cart(targets["prod2_id"], quantity=1)
    state.add_to_cart(targets["prod4_id"], quantity=1)
    state.add_to_cart(targets["prod5_id"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _curate_and_buy(state, targets)

    task = get_task("amazon_wishlist_curation")
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

    task = get_task("amazon_wishlist_curation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_bought_expensive_items_fails():
    _, _, targets, initial, state = _setup_session()

    # Buy all 5 instead of filtering
    for pid_key in ("prod1_id", "prod2_id", "prod3_id", "prod4_id", "prod5_id"):
        state.add_to_cart(targets[pid_key], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_wishlist_curation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_one_item_fails():
    _, _, targets, initial, state = _setup_session()

    # Buy only 2 of 3 cheap items
    state.add_to_cart(targets["prod2_id"], quantity=1)
    state.add_to_cart(targets["prod4_id"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker")
    pm = next(p for p in state.payment_methods if p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_wishlist_curation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
