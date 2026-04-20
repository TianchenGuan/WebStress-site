"""End-to-end tests for gmail_mark_all_read canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_mark_all_read',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Mark all 5 unread emails as read — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    for eid in targets["unread_email_ids"]:
        state.mark_read(eid, is_read=True)

    task = get_task('gmail_mark_all_read')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False (Class 1 guard)."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_mark_all_read')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_partial_read_fails():
    """Mark only some unread emails as read — bijection under-saturated, passed=False."""
    _, _, targets, initial, state = _setup_session()
    unread_ids = targets["unread_email_ids"]
    # Mark only first 2 of 5
    for eid in unread_ids[:2]:
        state.mark_read(eid, is_read=True)

    task = get_task('gmail_mark_all_read')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "marking only some unread emails should fail"
    assert report.score < 1.0


def test_excess_read_fails():
    """Mark all unread plus send an email — invariant violation on sent, passed=False."""
    _, _, targets, initial, state = _setup_session()
    for eid in targets["unread_email_ids"]:
        state.mark_read(eid, is_read=True)
    # Send an unsolicited email
    state.send_email(subject="Extra", body="Oops", to=["a@b.com"])

    task = get_task('gmail_mark_all_read')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "sending extra email should trigger invariant violation"
