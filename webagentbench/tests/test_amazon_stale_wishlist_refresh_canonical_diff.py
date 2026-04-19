"""End-to-end tests for amazon_stale_wishlist_refresh canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_stale_wishlist_refresh",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _refresh_wishlist(state, targets):
    """Remove OOS items from wishlist and add in-stock replacements in same category."""
    alts = targets["alternative_product_ids"]
    for idx, pid in enumerate(targets["oos_product_ids"]):
        state.remove_from_wishlist(pid)
        # Add one alternative per removed OOS item
        state.add_to_wishlist(alts[idx])


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _refresh_wishlist(state, targets)

    task = get_task("amazon_stale_wishlist_refresh")
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

    task = get_task("amazon_stale_wishlist_refresh")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_removed_but_no_replacement_fails():
    """Removing OOS items but adding no replacements should violate size constraint."""
    _, _, targets, initial, state = _setup_session()
    for pid in targets["oos_product_ids"]:
        state.remove_from_wishlist(pid)

    task = get_task("amazon_stale_wishlist_refresh")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_removed_in_stock_kept_fails():
    """Accidentally removing the in-stock kept item should fail."""
    _, _, targets, initial, state = _setup_session()
    _refresh_wishlist(state, targets)
    # Oops: remove the item we should have kept
    state.remove_from_wishlist(targets["in_stock_kept_id"][0])
    # Replace with yet another alternative so the size is still the same
    alts = targets["alternative_product_ids"]
    state.add_to_wishlist(alts[2])

    task = get_task("amazon_stale_wishlist_refresh")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_replacement_in_wrong_category_fails():
    """Adding replacement from the wrong category should fail."""
    _, _, targets, initial, state = _setup_session()
    for pid in targets["oos_product_ids"]:
        state.remove_from_wishlist(pid)
    # Add replacements NOT in target category (pick in-stock from Books or elsewhere)
    wrong_cat_candidates = [
        p for p in state.products
        if p.in_stock
        and p.category != targets["category_of_oos"]
        and p.id not in initial.wishlist
        and p.id not in targets["oos_product_ids"]
    ]
    assert len(wrong_cat_candidates) >= 2
    state.add_to_wishlist(wrong_cat_candidates[0].id)
    state.add_to_wishlist(wrong_cat_candidates[1].id)

    task = get_task("amazon_stale_wishlist_refresh")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
