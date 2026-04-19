"""End-to-end tests for amazon_cart_recover_from_oos canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_cart_recover_from_oos",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _swap_cart(state, targets):
    """Remove every OOS cart item and add an in-stock alternative per OOS slot."""
    alts = targets["alternative_product_ids"]
    for idx, item_id in enumerate(targets["oos_cart_item_ids"]):
        state.remove_from_cart(item_id)
        state.add_to_cart(alts[idx], quantity=1)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _swap_cart(state, targets)

    task = get_task("amazon_cart_recover_from_oos")
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

    task = get_task("amazon_cart_recover_from_oos")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_removed_but_no_replacement_fails():
    """Removing OOS items but adding no replacements should fail the bijection."""
    _, _, targets, initial, state = _setup_session()
    for item_id in targets["oos_cart_item_ids"]:
        state.remove_from_cart(item_id)

    task = get_task("amazon_cart_recover_from_oos")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_removed_kept_item_fails():
    """Accidentally removing the in-stock kept cart item should fail."""
    _, _, targets, initial, state = _setup_session()
    _swap_cart(state, targets)
    # Accidentally remove the kept item
    state.remove_from_cart(targets["kept_cart_item_id"][0])

    task = get_task("amazon_cart_recover_from_oos")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_replacement_in_wrong_category_fails():
    """Adding replacement from a different category should fail."""
    _, _, targets, initial, state = _setup_session()
    for item_id in targets["oos_cart_item_ids"]:
        state.remove_from_cart(item_id)
    # Pick in-stock items in a DIFFERENT category (Electronics, not Office Supplies)
    wrong_candidates = [
        p for p in state.products
        if p.in_stock and p.category != targets["oos_category"]
        and p.id not in targets["oos_product_ids"]
    ]
    assert len(wrong_candidates) >= 2
    state.add_to_cart(wrong_candidates[0].id, quantity=1)
    state.add_to_cart(wrong_candidates[1].id, quantity=1)

    task = get_task("amazon_cart_recover_from_oos")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
