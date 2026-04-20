"""End-to-end tests for gmail_briefing_under_fire canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_briefing_under_fire',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Compile board briefing email + delete spam — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    body = (
        f"Board Briefing — {targets['meeting_date']}\n\n"
        f"Topic A: {targets['update_a']}\n"
        f"Topic B: {targets['update_b']}\n"
        f"Topic C: {targets['update_c']}"
    )
    state.send_email(
        subject=f"Board Briefing — {targets['meeting_date']}",
        body=body,
        to=[targets["ceo_email"]],
    )
    state.delete_email(targets["spam_email_id"])

    task = get_task('gmail_briefing_under_fire')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_briefing_under_fire')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_update_fails():
    """Send briefing without one of the thread updates — body check fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject=f"Board Briefing — {targets['meeting_date']}",
        body=f"Topic A: {targets['update_a']}\nTopic B: {targets['update_b']}",  # missing update_c
        to=[targets["ceo_email"]],
    )
    state.delete_email(targets["spam_email_id"])

    task = get_task('gmail_briefing_under_fire')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing update_c should fail"
