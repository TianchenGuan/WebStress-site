"""End-to-end tests for amazon_spec_comparison canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_spec_comparison",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    state.add_to_browsing_history(targets["monitor_a_id"])
    state.add_to_browsing_history(targets["monitor_b_id"])

    task = get_task("amazon_spec_comparison")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    # Read-only task moved to Cat-D (canonical_diff has invariants only).
    # View-tracking is now enforced by the eval block, not canonical_diff,
    # so do-nothing legitimately scores 1.0 here. Eval block separately
    # asserts the agent visited the required pages.
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_price_research")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True  # invariants hold; eval block enforces view-tracking
    assert report.score == 1.0


def test_added_to_cart_fails():
    _, _, targets, initial, state = _setup_session()

    state.add_to_browsing_history(targets["monitor_a_id"])
    state.add_to_browsing_history(targets["monitor_b_id"])
    # Agent wrongly adds to cart
    state.add_to_cart(targets["monitor_a_id"], quantity=1)

    task = get_task("amazon_spec_comparison")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False

# Removed: test_wrong_product_viewed_fails — view-tracking moved to eval block, not canonical_diff.