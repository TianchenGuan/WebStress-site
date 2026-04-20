"""End-to-end tests for gmail_verify_inbox_clean canonical_diff.

This is a read-only verification task — the correct trajectory is to do nothing.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_verify_inbox_clean',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Do nothing — inbox is already clean, score=1.0."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_verify_inbox_clean')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_deleting_email_fails():
    """Deleting an email violates the preserve-all invariant — should fail."""
    _, _, targets, initial, state = _setup_session()
    # Pick any inbox email to delete
    email_id = state.emails[0].id
    state.delete_email(email_id)

    task = get_task('gmail_verify_inbox_clean')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "deleting email should violate invariant"


def test_sending_email_fails():
    """Sending a new email violates the preserve-all sent invariant — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(subject="Unnecessary", body="Off-task email", to=["test@example.com"])

    task = get_task('gmail_verify_inbox_clean')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "sending email should violate preserve-sent invariant"
