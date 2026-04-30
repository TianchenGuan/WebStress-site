"""End-to-end tests for gmail_schedule_recovery canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_schedule_recovery',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    state.send_email(
        subject="Re: Q2 Planning Sync — Time Proposal",
        body="Disregard my previous confirmation. The correct time is Thursday, 2:00 PM.",
        to=[targets["hana_email"]],
        in_reply_to=targets["cancellation_email_id"],
    )


def test_correct_trajectory_passes():
    """Send correction reply — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_schedule_recovery')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_schedule_recovery')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_body_fails():
    """Send reply with wrong body (missing required phrases) — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Q2 Planning Sync — Time Proposal",
        body="I'll be there at the agreed time.",  # missing required phrases
        to=[targets["hana_email"]],
        in_reply_to=targets["cancellation_email_id"],
    )

    task = get_task('gmail_schedule_recovery')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing required phrases should fail"


def test_extra_body_text_fails():
    """The correction reply requires the exact text, not a longer message."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Q2 Planning Sync — Time Proposal",
        body=(
            "Disregard my previous confirmation. "
            "The correct time is Thursday, 2:00 PM. Thanks!"
        ),
        to=[targets["hana_email"]],
        in_reply_to=targets["cancellation_email_id"],
    )

    task = get_task('gmail_schedule_recovery')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "extra body text should fail"
