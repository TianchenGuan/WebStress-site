"""End-to-end tests for gmail_contact_deduplication canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_contact_deduplication',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Delete outdated contact + update surviving contact note — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.remove_contact(targets["outdated_contact_id"])
    state.update_contact(targets["surviving_contact_id"], note="Verified active — March 2026")

    task = get_task('gmail_contact_deduplication')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_contact_deduplication')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_contact_deleted_fails():
    """Delete the surviving contact instead — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.remove_contact(targets["surviving_contact_id"])  # wrong contact deleted

    task = get_task('gmail_contact_deduplication')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "deleting wrong contact should fail"


def test_wrong_note_fails():
    """Delete correct contact but set wrong note — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.remove_contact(targets["outdated_contact_id"])
    state.update_contact(targets["surviving_contact_id"], note="Wrong note text")

    task = get_task('gmail_contact_deduplication')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong note should fail"
