"""End-to-end tests for amazon_prime_enable_and_free_shipping canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_prime_enable_and_free_shipping",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _enable_prime_and_order(state, targets):
    state.settings.prime_member = True
    state.add_to_cart(targets["product_id"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    return state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    order = _enable_prime_and_order(state, targets)
    assert order.shipping_cost == 0.0, f"expected $0 shipping, got ${order.shipping_cost}"

    task = get_task("amazon_prime_enable_and_free_shipping")
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

    task = get_task("amazon_prime_enable_and_free_shipping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_order_without_prime_fails():
    """Placing the order without enabling Prime = $5.99 shipping on sub-$25 order."""
    _, _, targets, initial, state = _setup_session()

    state.add_to_cart(targets["product_id"], quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    order = state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)
    assert order.shipping_cost > 0.0, "expected non-zero shipping without Prime"

    task = get_task("amazon_prime_enable_and_free_shipping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_prime_enabled_but_no_order_fails():
    _, _, targets, initial, state = _setup_session()

    state.settings.prime_member = True

    task = get_task("amazon_prime_enable_and_free_shipping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_product_fails():
    _, _, targets, initial, state = _setup_session()

    state.settings.prime_member = True
    wrong = next(p.id for p in state.products if p.id != targets["product_id"])
    state.add_to_cart(wrong, quantity=1)
    addr = next(a for a in state.addresses if a.is_default)
    pm = next(p for p in state.payment_methods if p.is_default)
    state.place_order(shipping_address_id=addr.id, payment_method_id=pm.id)

    task = get_task("amazon_prime_enable_and_free_shipping")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
