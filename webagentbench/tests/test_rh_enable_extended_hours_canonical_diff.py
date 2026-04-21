"""End-to-end tests for rh_enable_extended_hours canonical_diff.

Task: "Enable extended hours trading in your account settings."

Verifies:
  - Correct trajectory (enable extended hours) passes with score 1.0.
  - No action (setting stays disabled) fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_enable_extended_hours",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.update_settings(extended_hours_enabled=True)

    task = get_task("rh_enable_extended_hours")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_action_fails():
    """Agent does nothing — extended hours remains disabled."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("rh_enable_extended_hours")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "not enabling extended hours should fail — constraint requires extended_hours_enabled=True"
    )
