"""End-to-end tests for amazon_cart_management canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_cart_management",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _fix_cart(state, targets):
    rm = next(it for it in state.cart_items if it.product_name == targets["remove_product"])
    state.remove_from_cart(rm.id)
    upd = next(it for it in state.cart_items if it.product_name == targets["update_product"])
    state.update_cart_quantity(upd.id, int(targets["new_quantity"]))


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _fix_cart(state, targets)

    task = get_task("amazon_cart_management")
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

    task = get_task("amazon_cart_management")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_wrong_quantity_fails():
    _, _, targets, initial, state = _setup_session()

    rm = next(it for it in state.cart_items if it.product_name == targets["remove_product"])
    state.remove_from_cart(rm.id)
    upd = next(it for it in state.cart_items if it.product_name == targets["update_product"])
    state.update_cart_quantity(upd.id, 5)  # wrong

    task = get_task("amazon_cart_management")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_did_not_remove_fails():
    _, _, targets, initial, state = _setup_session()

    upd = next(it for it in state.cart_items if it.product_name == targets["update_product"])
    state.update_cart_quantity(upd.id, int(targets["new_quantity"]))

    task = get_task("amazon_cart_management")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_removed_wrong_item_fails():
    _, _, targets, initial, state = _setup_session()

    # Accidentally remove Laptop Stand
    wrong = next(it for it in state.cart_items if it.product_name == "Laptop Stand")
    state.remove_from_cart(wrong.id)
    upd = next(it for it in state.cart_items if it.product_name == targets["update_product"])
    state.update_cart_quantity(upd.id, int(targets["new_quantity"]))

    task = get_task("amazon_cart_management")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
