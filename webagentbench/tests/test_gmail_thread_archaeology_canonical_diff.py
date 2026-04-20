"""End-to-end tests for gmail_thread_archaeology canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_thread_archaeology',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Forward thread to assignee with manager CC and deadline in body
    state.forward_email(
        targets["thread_email_id"],
        to=[targets["assignee_email"]],
        cc=[targets["manager_email"]],
        body=f"Please handle action item by deadline: {targets['deadline']}",
    )
    # Create Pending Action label
    state.ensure_label("Pending Action")
    # Reply to thread confirming delegation
    state.send_email(
        subject=f"Re: {targets['thread_subject']}",
        body="I have delegated this action item.",
        to=[targets["assignee_email"]],
        in_reply_to=targets["thread_email_id"],
    )
    # Star thread email and apply Pending Action label
    state.toggle_star(targets["thread_email_id"], is_starred=True)
    state.apply_label(targets["thread_email_id"], "Pending Action", action='add')


def test_correct_trajectory_passes():
    """Apply all thread archaeology actions — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_thread_archaeology')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_thread_archaeology')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_forward_recipient_fails():
    """Forward to wrong person — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.forward_email(
        targets["thread_email_id"],
        to=[targets["wrong_person_email"]],  # wrong recipient
        cc=[targets["manager_email"]],
        body=f"Deadline: {targets['deadline']}",
    )
    state.ensure_label("Pending Action")
    state.send_email(
        subject=f"Re: {targets['thread_subject']}",
        body="I have delegated this.",
        to=[targets["wrong_person_email"]],
        in_reply_to=targets["thread_email_id"],
    )
    state.toggle_star(targets["thread_email_id"], is_starred=True)
    state.apply_label(targets["thread_email_id"], "Pending Action", action='add')

    task = get_task('gmail_thread_archaeology')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "forwarding to wrong person should fail"
