"""End-to-end tests for gmail_reply_simple canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_reply_simple',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Send exact reply body in correct thread — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Meeting Tomorrow at 2pm",
        body="I'll be there. Thanks!",
        to=["bob.martinez@example.com"],
        thread_id=targets["target_thread_id"],
        in_reply_to=targets["target_email_id"],
    )

    task = get_task('gmail_reply_simple')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No email sent — score=0, passed=False (Class 1 guard)."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_reply_simple')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_body_fails():
    """Reply with wrong body text — predicate fails, passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Meeting Tomorrow at 2pm",
        body="I can't make it.",  # wrong body
        to=["bob.martinez@example.com"],
        thread_id=targets["target_thread_id"],
        in_reply_to=targets["target_email_id"],
    )

    task = get_task('gmail_reply_simple')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong body should fail"


def test_wrong_thread_fails():
    """Reply to correct email but with wrong thread_id — identity check fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Meeting Tomorrow at 2pm",
        body="I'll be there. Thanks!",
        to=["bob.martinez@example.com"],
        thread_id="thread_wrong_99",  # wrong thread
        in_reply_to=targets["target_email_id"],
    )

    task = get_task('gmail_reply_simple')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong thread_id should fail"


def test_forward_instead_of_reply_fails():
    """Forward the email instead of replying — forwarded_from_id != null, fails."""
    _, _, targets, initial, state = _setup_session()
    state.forward_email(targets["target_email_id"], to=["someone@example.com"])

    task = get_task('gmail_reply_simple')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "forward should not satisfy a reply task"
