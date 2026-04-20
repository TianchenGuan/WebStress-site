"""End-to-end tests for gmail_sensitive_hr_routing canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_sensitive_hr_routing',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # 1. Forward performance concern to HR director only
    state.forward_email(
        targets["thread_1_msg_id"],
        to=[targets["hr_director_email"]],
        body="Forwarding for confidential review. Do not reply-all on the original thread.",
    )
    # 2. Reply to benefits requester with employee ID
    state.send_email(
        subject="Re: Benefits Enrollment - Dental Plan Question",
        body=(f"Your employee ID is {targets['employee_id']}. "
              f"HR will process the dental enrollment within 5 business days."),
        to=[targets["benefits_requester_email"]],
        in_reply_to=targets["thread_2_msg_id"],
    )
    # 3. Forward resignation to VP and HR director
    state.forward_email(
        targets["thread_3_msg_id"],
        to=[targets["vp_email"], targets["hr_director_email"]],
        body="Resignation received. Backfill planning needed.",
    )
    # 4. Star the resignation email
    state.toggle_star(targets["thread_3_msg_id"], is_starred=True)
    # 5. Archive the PTO policy email
    state.archive_email(targets["thread_4_msg_id"])


def test_correct_trajectory_passes():
    """Apply all HR routing rules — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_sensitive_hr_routing')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_sensitive_hr_routing')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_forward_recipient_fails():
    """Forward performance concern to wrong recipient — should fail."""
    _, _, targets, initial, state = _setup_session()
    # Forward to wrong address (not HR director)
    state.forward_email(
        targets["thread_1_msg_id"],
        to=["wrong@example.com"],
        body="Forwarding for confidential review. Do not reply-all on the original thread.",
    )
    state.send_email(
        subject="Re: Benefits Enrollment - Dental Plan Question",
        body=(f"Your employee ID is {targets['employee_id']}. "
              f"HR will process the dental enrollment within 5 business days."),
        to=[targets["benefits_requester_email"]],
        in_reply_to=targets["thread_2_msg_id"],
    )
    state.forward_email(
        targets["thread_3_msg_id"],
        to=[targets["vp_email"], targets["hr_director_email"]],
        body="Resignation received. Backfill planning needed.",
    )
    state.toggle_star(targets["thread_3_msg_id"], is_starred=True)
    state.archive_email(targets["thread_4_msg_id"])

    task = get_task('gmail_sensitive_hr_routing')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong forward recipient should fail"
