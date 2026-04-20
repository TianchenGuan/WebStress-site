"""End-to-end tests for gmail_thread_detective canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_thread_detective',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Find the most recent email in the scheduling thread to reply to
    thread_emails = [e for e in state.emails
                     if e.thread_id == targets["most_recent_thread_id"]]
    # Sort by timestamp to get the most recent
    most_recent = max(thread_emails, key=lambda e: e.timestamp)
    state.send_email(
        subject=f"Re: {most_recent.subject}",
        body=f"{targets['correct_time']} works for me. Looking forward to it!",
        to=[targets["sender_email"]],
        in_reply_to=most_recent.id,
    )


def test_correct_trajectory_passes():
    """Reply confirming correct non-conflicting time — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_thread_detective')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_thread_detective')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_time_in_body_fails():
    """Reply with wrong time (a conflicting time) — should fail."""
    _, _, targets, initial, state = _setup_session()
    thread_emails = [e for e in state.emails
                     if e.thread_id == targets["most_recent_thread_id"]]
    most_recent = max(thread_emails, key=lambda e: e.timestamp)
    wrong_time = targets["wrong_times"][0]  # pick a conflicting time
    state.send_email(
        subject=f"Re: {most_recent.subject}",
        body=f"{wrong_time} works for me.",  # wrong time
        to=[targets["sender_email"]],
        in_reply_to=most_recent.id,
    )

    task = get_task('gmail_thread_detective')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong time in reply should fail"
