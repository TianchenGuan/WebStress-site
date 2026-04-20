"""End-to-end tests for gmail_contact_cleanup canonical_diff."""

from webagentbench.backend.models.gmail import Contact
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_contact_cleanup',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Delete 2 stale contacts, add missing contact with required note — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.remove_contact(targets["stale_contact_id_a"])
    state.remove_contact(targets["stale_contact_id_b"])
    state.add_contact(Contact(
        id='c_missing',
        name=targets["missing_contact_name"],
        email=targets["missing_contact_email"],
        note=targets["contact_note"],
    ))

    task = get_task('gmail_contact_cleanup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_contact_cleanup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_note_fails():
    """Add contact with wrong note — property check fails."""
    _, _, targets, initial, state = _setup_session()
    state.remove_contact(targets["stale_contact_id_a"])
    state.remove_contact(targets["stale_contact_id_b"])
    state.add_contact(Contact(
        id='c_missing2',
        name=targets["missing_contact_name"],
        email=targets["missing_contact_email"],
        note="This is the wrong note",  # wrong note
    ))

    task = get_task('gmail_contact_cleanup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong contact note should fail"
