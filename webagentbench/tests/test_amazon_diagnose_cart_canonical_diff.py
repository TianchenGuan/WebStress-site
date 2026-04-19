"""End-to-end tests for amazon_diagnose_cart canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_diagnose_cart",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _fix_cart(state, targets):
    # Remove OOS item
    oos = next(it for it in state.cart_items if it.product_id == targets["oos_product_id"])
    state.remove_from_cart(oos.id)
    # Update target quantity to correct_qty
    tgt = next(it for it in state.cart_items if it.product_id == targets["product_id"])
    state.update_cart_quantity(tgt.id, targets["correct_qty"])


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _fix_cart(state, targets)

    task = get_task("amazon_diagnose_cart")
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

    task = get_task("amazon_diagnose_cart")
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

    oos = next(it for it in state.cart_items if it.product_id == targets["oos_product_id"])
    state.remove_from_cart(oos.id)
    tgt = next(it for it in state.cart_items if it.product_id == targets["product_id"])
    # Wrong quantity
    state.update_cart_quantity(tgt.id, targets["correct_qty"] + 1)

    task = get_task("amazon_diagnose_cart")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_did_not_remove_oos_fails():
    _, _, targets, initial, state = _setup_session()

    tgt = next(it for it in state.cart_items if it.product_id == targets["product_id"])
    state.update_cart_quantity(tgt.id, targets["correct_qty"])

    task = get_task("amazon_diagnose_cart")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_removed_kept_item_fails():
    _, _, targets, initial, state = _setup_session()

    oos = next(it for it in state.cart_items if it.product_id == targets["oos_product_id"])
    state.remove_from_cart(oos.id)
    tgt = next(it for it in state.cart_items if it.product_id == targets["product_id"])
    state.update_cart_quantity(tgt.id, targets["correct_qty"])
    # Accidentally remove the extra/kept item
    extra = next(it for it in state.cart_items if it.product_id == targets["extra_product_id"])
    state.remove_from_cart(extra.id)

    task = get_task("amazon_diagnose_cart")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
