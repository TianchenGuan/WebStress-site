"""End-to-end tests for gmail_confidential_forwarding canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_confidential_forwarding',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Send 2 new emails with quotes + star 2 thread emails — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Q3 Numbers for Your Review",
        body=targets["q3_quote"],
        to=[targets["q3_recipient"]],
    )
    state.send_email(
        subject="M&A Pipeline Extract",
        body=targets["ma_quote"],
        to=[targets["ma_recipient"]],
    )
    state.toggle_star(targets["q3_star_email_id"], is_starred=True)
    state.toggle_star(targets["ma_star_email_id"], is_starred=True)

    task = get_task('gmail_confidential_forwarding')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_confidential_forwarding')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_quote_fails():
    """Send email with wrong quote text — body check fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Q3 Numbers for Your Review",
        body="Some wrong quote text here",  # wrong quote
        to=[targets["q3_recipient"]],
    )
    state.send_email(
        subject="M&A Pipeline Extract",
        body=targets["ma_quote"],
        to=[targets["ma_recipient"]],
    )
    state.toggle_star(targets["q3_star_email_id"], is_starred=True)
    state.toggle_star(targets["ma_star_email_id"], is_starred=True)

    task = get_task('gmail_confidential_forwarding')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong quote should fail"
