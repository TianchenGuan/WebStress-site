"""End-to-end tests for gmail_change_setting canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_change_setting',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Set undo_send_seconds to 30 — constraint passes, score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.settings.undo_send_seconds = 30

    task = get_task('gmail_change_setting')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    # constraints are penalty-only; score starts at 0 total_weight when no
    # create/update/delete entries — validate the constraint passes at minimum.
    assert len([f for f in report.failures if "constraint" in f.kind]) == 0


def test_do_nothing_fails():
    """Do nothing — undo_send_seconds stays at 5, constraint fails."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_change_setting')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False


def test_wrong_value_fails():
    """Set undo_send_seconds to 10 instead of 30 — constraint fails."""
    _, _, targets, initial, state = _setup_session()
    state.settings.undo_send_seconds = 10  # wrong value

    task = get_task('gmail_change_setting')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong undo_send_seconds value should fail constraint"


def test_correct_setting_plus_sent_email_fails():
    """Set correct delay but also send an unsolicited email — invariant violation."""
    _, _, targets, initial, state = _setup_session()
    state.settings.undo_send_seconds = 30
    state.send_email(subject="Extra", body="Oops", to=["x@y.com"])

    task = get_task('gmail_change_setting')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "extra email sent should trigger invariant violation"
