"""End-to-end tests for rh_verify_no_action_needed canonical_diff.

Task: VOO (cost_basis=650, current~437, -33%) and SCHD (cost_basis=120,
current~78, -35%) have dropped >30% from purchase price. Agent must pause
those two recurring investments while leaving AAPL and MSFT untouched.

Verifies:
  - Pausing VOO and SCHD RIs passes.
  - Leaving RIs unchanged fails (missing required pauses).
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_verify_no_action_needed",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_no_action_passes():
    """Correct behavior: pause VOO and SCHD RIs (both dropped >30%)."""
    sm, sid, targets, initial, state = _setup_session()
    # VOO dropped ~33% and SCHD dropped ~35% from purchase price — pause both.
    for ri in state.recurring_investments:
        if ri.symbol in ("VOO", "SCHD"):
            state.update_recurring_investment(ri.id, status="paused")

    task = get_task("rh_verify_no_action_needed")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_pausing_ri_fails():
    """Pausing only AAPL (wrong target) while missing VOO/SCHD should fail."""
    sm, sid, targets, initial, state = _setup_session()
    # Pause AAPL (which should NOT be paused) while leaving VOO/SCHD active.
    aapl_ri = next((r for r in state.recurring_investments if r.symbol == "AAPL"), None)
    if aapl_ri:
        state.update_recurring_investment(aapl_ri.id, status="paused")

    task = get_task("rh_verify_no_action_needed")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "pausing AAPL instead of VOO/SCHD should fail"
