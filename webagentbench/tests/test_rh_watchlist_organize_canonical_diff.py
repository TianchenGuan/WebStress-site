"""End-to-end tests for rh_watchlist_organize canonical_diff.

Task: Create "Tech Leaders" watchlist (AAPL, MSFT, GOOGL, NVDA, META) and
"Dividend Kings" watchlist (KO, JNJ, PG, XOM, HD).

Verifies:
  - Correct trajectory (both watchlists with correct symbols) passes.
  - Wrong watchlist name fails.
  - Duplicate watchlist fails (constraint violation).
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_watchlist_organize",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.create_watchlist("Tech Leaders", ["AAPL", "MSFT", "GOOGL", "NVDA", "META"])
    state.create_watchlist("Dividend Kings", ["KO", "JNJ", "PG", "XOM", "HD"])

    task = get_task("rh_watchlist_organize")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_watchlist_name_fails():
    """Agent creates watchlists with wrong names."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_watchlist("Tech Giants", ["AAPL", "MSFT", "GOOGL", "NVDA", "META"])
    state.create_watchlist("Dividend Kings", ["KO", "JNJ", "PG", "XOM", "HD"])

    task = get_task("rh_watchlist_organize")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wrong watchlist name should fail"


def test_missing_symbols_fails():
    """Agent creates Tech Leaders missing some required symbols."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_watchlist("Tech Leaders", ["AAPL", "MSFT"])  # missing GOOGL, NVDA, META
    state.create_watchlist("Dividend Kings", ["KO", "JNJ", "PG", "XOM", "HD"])

    task = get_task("rh_watchlist_organize")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing required symbols should fail"


def test_duplicate_watchlist_fails():
    """Agent creates two Tech Leaders watchlists — violates uniqueness constraint."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_watchlist("Tech Leaders", ["AAPL", "MSFT", "GOOGL", "NVDA", "META"])
    state.create_watchlist("Tech Leaders", ["AAPL", "MSFT", "GOOGL", "NVDA", "META"])
    state.create_watchlist("Dividend Kings", ["KO", "JNJ", "PG", "XOM", "HD"])

    task = get_task("rh_watchlist_organize")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "duplicate Tech Leaders watchlist should fail constraint"
