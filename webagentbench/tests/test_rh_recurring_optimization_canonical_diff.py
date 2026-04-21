"""End-to-end tests for rh_recurring_optimization canonical_diff.

Task: Pause recurring investments where avg purchase price is >5% above
current price, and pause those for stocks with earnings in next 3 days.

Verifies:
  - Correct pause trajectory passes.
  - Pausing extra (non-should-pause) RIs fails.
  - Missing pause for overpaying RI fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_recurring_optimization",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_optimization(state, targets):
    for sym in targets["should_pause_symbols"]:
        ri = next(
            (r for r in state.recurring_investments if r.symbol == sym and r.status == "active"),
            None,
        )
        if ri:
            state.update_recurring_investment(ri.id, status="paused")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_optimization(state, targets)

    task = get_task("rh_recurring_optimization")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_pausing_extra_ri_fails():
    """Agent pauses an RI that should remain active."""
    sm, sid, targets, initial, state = _setup_session()
    _do_optimization(state, targets)

    # Also pause an extra RI that shouldn't be paused
    extra = next(
        (r for r in state.recurring_investments if r.symbol not in targets["should_pause_symbols"] and r.status == "active"),
        None,
    )
    if extra:
        state.update_recurring_investment(extra.id, status="paused")

    task = get_task("rh_recurring_optimization")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "pausing extra RI should fail"


def test_missing_pause_fails():
    """Agent pauses only some of the should-pause RIs, missing one."""
    sm, sid, targets, initial, state = _setup_session()
    should_pause = targets["should_pause_symbols"]
    assert len(should_pause) >= 2, "Need at least 2 should-pause symbols"

    # Pause all but the last
    for sym in should_pause[:-1]:
        ri = next(
            (r for r in state.recurring_investments if r.symbol == sym and r.status == "active"),
            None,
        )
        if ri:
            state.update_recurring_investment(ri.id, status="paused")

    task = get_task("rh_recurring_optimization")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing pause for one RI should fail"
