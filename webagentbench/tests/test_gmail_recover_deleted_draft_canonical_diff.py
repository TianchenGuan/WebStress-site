"""End-to-end tests for gmail_recover_deleted_draft canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_recover_deleted_draft',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    state.send_email(
        subject=targets["draft_subject"],
        body=(f"Hi {targets['recipient_name']},\n\n"
              f"{targets['key_point_1']} {targets['key_point_2']} {targets['key_point_3']}"),
        to=[targets["recipient_email"]],
    )


def test_correct_trajectory_passes():
    """Send recovered draft — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_recover_deleted_draft')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_recover_deleted_draft')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_recipient_fails():
    """Send to wrong recipient — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject=targets["draft_subject"],
        body=(f"{targets['key_point_1']} {targets['key_point_2']} {targets['key_point_3']}"),
        to=["wrong@example.com"],
    )

    task = get_task('gmail_recover_deleted_draft')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong recipient should fail"
