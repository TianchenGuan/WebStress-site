"""End-to-end tests for rh_add_to_watchlist canonical_diff.

Task: 'Add NVDA to your "Tech Stocks" watchlist.'

Verifies:
  - Correct trajectory (NVDA added to Tech Stocks) passes with score 1.0.
  - Wrong watchlist (NVDA added to a different watchlist) fails.
  - NVDA not added at all fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_add_to_watchlist",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.add_to_watchlist(targets["watchlist_id"], "NVDA")

    task = get_task("rh_add_to_watchlist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    """Agent does nothing — NVDA never added."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("rh_add_to_watchlist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "no mutation should fail — NVDA membership constraint must fire"
    )


def test_wrong_watchlist_fails():
    """Agent adds NVDA to a different watchlist, not Tech Stocks."""
    sm, sid, targets, initial, state = _setup_session()
    from webagentbench.backend.models.robinhood import Watchlist
    import datetime
    other = Watchlist(
        id="wl_other_test",
        name="Other List",
        symbols=["NVDA"],
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    state.watchlists.append(other)

    task = get_task("rh_add_to_watchlist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "adding NVDA to the wrong watchlist should fail — constraint checks target watchlist"
    )
