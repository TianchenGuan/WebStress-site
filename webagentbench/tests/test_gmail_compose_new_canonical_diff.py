"""End-to-end tests for gmail_compose_new canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_compose_new',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Send exactly the required email — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Weekly Report",
        body="Hi Alice, please find the weekly report attached. Best regards.",
        to=["alice@thornton.com"],
    )

    task = get_task('gmail_compose_new')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No email sent — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_compose_new')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_recipient_fails():
    """Send to wrong address — identity check fails, passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Weekly Report",
        body="Hi Alice, please find the weekly report attached. Best regards.",
        to=["bob@thornton.com"],  # wrong recipient
    )

    task = get_task('gmail_compose_new')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong recipient should fail"


def test_wrong_subject_fails():
    """Send with wrong subject — predicate fails, passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Monthly Report",  # wrong subject
        body="Hi Alice, please find the weekly report attached. Best regards.",
        to=["alice@thornton.com"],
    )

    task = get_task('gmail_compose_new')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong subject should fail"
