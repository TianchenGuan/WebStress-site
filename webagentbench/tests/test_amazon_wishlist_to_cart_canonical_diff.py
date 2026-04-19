"""End-to-end tests for amazon_wishlist_to_cart canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_wishlist_to_cart",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _buy_wishlist(state, targets):
    state.add_to_cart(targets["product_id"], quantity=1)
    state.add_to_cart(targets["product_id_2"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker" and a.street_address == "742 Evergreen Terrace")
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _buy_wishlist(state, targets)

    task = get_task("amazon_wishlist_to_cart")
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

    task = get_task("amazon_wishlist_to_cart")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_address_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_to_cart(targets["product_id"], quantity=1)
    state.add_to_cart(targets["product_id_2"], quantity=1)
    # Different (Alex Parker) address
    addr = next(a for a in state.addresses if a.full_name == "Alex Parker")
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_wishlist_to_cart")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_only_one_item_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_to_cart(targets["product_id"], quantity=1)
    addr = next(a for a in state.addresses if a.full_name == "Jordan Parker" and a.street_address == "742 Evergreen Terrace")
    pm = next(p for p in state.payment_methods if p.card_type == "Visa" and p.last_four == "4242")
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_wishlist_to_cart")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
