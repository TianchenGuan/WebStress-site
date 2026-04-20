"""End-to-end tests for gmail_credential_leak_response canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_credential_leak_response',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Forward alert + star IT procedures email — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    state.forward_email(targets["alert_email_id"], to=[targets["forward_to"]])
    state.toggle_star(targets["star_email_id"], is_starred=True)

    task = get_task('gmail_credential_leak_response')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_credential_leak_response')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_email_forwarded_fails():
    """Forward wrong email instead — identity check fails, passed=False."""
    _, _, targets, initial, state = _setup_session()
    wrong_id = next(
        e.id for e in state.emails
        if e.id != targets["alert_email_id"] and e.id != targets["star_email_id"]
    )
    state.forward_email(wrong_id, to=[targets["forward_to"]])
    state.toggle_star(targets["star_email_id"], is_starred=True)

    task = get_task('gmail_credential_leak_response')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "forwarding wrong email should fail"
