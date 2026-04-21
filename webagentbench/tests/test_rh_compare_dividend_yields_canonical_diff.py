"""End-to-end tests for rh_compare_dividend_yields canonical_diff.

Task: Compare dividend yields of KO, PEP, PG; add highest yield (KO) to
"Dividend Kings" watchlist.

Verifies:
  - Correct trajectory (adding KO) passes.
  - Adding wrong symbol (PEP instead of KO) fails.
  - Adding multiple symbols fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_compare_dividend_yields",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    wl = state.watchlist_named("Dividend Kings")
    assert wl is not None
    state.add_to_watchlist(wl.id, "KO")

    task = get_task("rh_compare_dividend_yields")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_symbol_fails():
    """Agent adds PEP instead of KO (the highest yielder)."""
    sm, sid, targets, initial, state = _setup_session()
    wl = state.watchlist_named("Dividend Kings")
    state.add_to_watchlist(wl.id, "PEP")

    task = get_task("rh_compare_dividend_yields")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "adding PEP instead of KO should fail"


def test_multiple_symbols_fails():
    """Agent adds all three symbols instead of just the highest yielder."""
    sm, sid, targets, initial, state = _setup_session()
    wl = state.watchlist_named("Dividend Kings")
    for sym in ["KO", "PEP", "PG"]:
        state.add_to_watchlist(wl.id, sym)

    task = get_task("rh_compare_dividend_yields")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "adding all three symbols should fail uniqueness constraint"
