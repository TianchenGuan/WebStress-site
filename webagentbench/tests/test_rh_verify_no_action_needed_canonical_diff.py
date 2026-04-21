"""End-to-end tests for rh_verify_no_action_needed canonical_diff.

Task: Review recurring investments; since none dropped 30%+, take no action.

Verifies:
  - Taking no action passes (all RIs remain active).
  - Incorrectly pausing an RI fails.
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
    """Correct behavior: no stocks dropped 30%+, so no RI changes needed."""
    sm, sid, targets, initial, state = _setup_session()
    # No state changes

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
    """Agent incorrectly pauses a recurring investment when none should be paused."""
    sm, sid, targets, initial, state = _setup_session()
    ri = next((r for r in state.recurring_investments if r.status == "active" and not r.id.startswith("ri_decoy_")), None)
    if ri:
        state.update_recurring_investment(ri.id, status="paused")

    task = get_task("rh_verify_no_action_needed")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "pausing an RI should fail"
