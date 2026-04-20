"""End-to-end tests for gmail_meeting_negotiation canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_meeting_negotiation',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    state.send_email(
        subject=f"Re: {targets['meeting_name']} Confirmation",
        body=f"The meeting is confirmed for {targets['correct_time']} in {targets['room_name']}.",
        to=[targets["organizer_email"]],
        cc=targets["attendee_emails"],
    )


def test_correct_trajectory_passes():
    """Confirmation email sent to organizer with time, room, all attendees CC'd — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_meeting_negotiation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No email sent — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_meeting_negotiation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_recipient_fails():
    """Send to wrong recipient — passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Meeting Confirmation",
        body=f"Confirmed for {targets['correct_time']} in {targets['room_name']}.",
        to=["wrong@example.com"],  # wrong recipient
        cc=targets["attendee_emails"],
    )

    task = get_task('gmail_meeting_negotiation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong recipient should fail"
