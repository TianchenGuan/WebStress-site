"""End-to-end tests for gmail_thread_version_conflict canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_thread_version_conflict',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    state.send_email(
        subject="Re: Release Version for Q3 Launch",
        body=f"{targets['reply_text']} Let me know if you need anything else.",
        to=[targets["chen_wei_email"]],
        in_reply_to=targets["chen_wei_latest_email_id"],
    )


def test_correct_trajectory_passes():
    """Reply with agreed version confirmation — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_thread_version_conflict')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_thread_version_conflict')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_reply_text_fails():
    """Reply with text that doesn't start with correct reply_text — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Release Version for Q3 Launch",
        body="Sounds good, we'll go with the agreed version.",  # doesn't start with reply_text
        to=[targets["chen_wei_email"]],
        in_reply_to=targets["chen_wei_latest_email_id"],
    )

    task = get_task('gmail_thread_version_conflict')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong reply text should fail"
