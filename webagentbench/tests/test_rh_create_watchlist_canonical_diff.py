"""End-to-end tests for rh_create_watchlist canonical_diff.

Task: Create a new watchlist called "Dividend Kings" and add KO, PG, and JNJ to it.

Verifies:
  - Correct trajectory (watchlist created with all 3 symbols) passes with score 1.0.
  - Missing symbol fails.
  - Wrong name fails.
  - Extra watchlist created alongside correct one fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_create_watchlist",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.create_watchlist("Dividend Kings", ["KO", "PG", "JNJ"])

    task = get_task("rh_create_watchlist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_symbol_fails():
    """Agent creates watchlist with only KO and PG, missing JNJ."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_watchlist("Dividend Kings", ["KO", "PG"])

    task = get_task("rh_create_watchlist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "missing JNJ should fail — set_eq predicate requires all 3 symbols"
    )


def test_wrong_name_fails():
    """Agent creates a watchlist with the right symbols but wrong name."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_watchlist("Dividend Stocks", ["KO", "PG", "JNJ"])

    task = get_task("rh_create_watchlist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "wrong watchlist name should fail — name eq predicate must reject it"
    )


def test_extra_watchlist_fails():
    """Agent correctly creates Dividend Kings AND an extra unrelated watchlist."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_watchlist("Dividend Kings", ["KO", "PG", "JNJ"])
    state.create_watchlist("Bonus List", ["AAPL"])

    task = get_task("rh_create_watchlist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "creating an extra watchlist should trigger unaccounted-mutation failure"
    )
