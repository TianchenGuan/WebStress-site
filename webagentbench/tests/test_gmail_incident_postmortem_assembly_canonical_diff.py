"""End-to-end tests for gmail_incident_postmortem_assembly canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_incident_postmortem_assembly',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Compose postmortem email with all required content
    state.send_email(
        subject=targets["postmortem_subject"],
        body=(
            f"Incident Start Time: {targets['start_time']}\n"
            f"Root Cause: {targets['corrected_root_cause']}\n"
            f"Resolution Time: {targets['resolution_time']}\n"
            f"Remediation: {targets['remediation']}"
        ),
        to=[targets["postmortem_to"]],
    )
    # Star all 5 incident anchor emails
    for eid in targets["incident_email_ids"]:
        state.toggle_star(eid, is_starred=True)


def test_correct_trajectory_passes():
    """Postmortem email sent and all incident emails starred — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_incident_postmortem_assembly')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_incident_postmortem_assembly')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_root_cause_fails():
    """Include wrong root cause instead of corrected one — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Use wrong_root_cause instead of corrected_root_cause
    state.send_email(
        subject=targets["postmortem_subject"],
        body=(
            f"Incident Start Time: {targets['start_time']}\n"
            f"Root Cause: {targets['wrong_root_cause']}\n"  # wrong!
            f"Resolution Time: {targets['resolution_time']}\n"
            f"Remediation: {targets['remediation']}"
        ),
        to=[targets["postmortem_to"]],
    )
    for eid in targets["incident_email_ids"]:
        state.toggle_star(eid, is_starred=True)

    task = get_task('gmail_incident_postmortem_assembly')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong root cause should fail"
