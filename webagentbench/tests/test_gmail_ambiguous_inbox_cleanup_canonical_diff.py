"""End-to-end tests for gmail_ambiguous_inbox_cleanup canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_ambiguous_inbox_cleanup',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Create project label, apply to project emails, star deadline emails, archive newsletters."""
    _, _, targets, initial, state = _setup_session()
    project_label = f"Project/{targets['project_name']}"
    state.ensure_label(project_label)
    for eid in targets["project_email_ids"]:
        state.apply_label(eid, project_label, action='add')
    for eid in targets["deadline_email_ids"]:
        state.toggle_star(eid, is_starred=True)
    for eid in targets["newsletter_ids"]:
        state.archive_email(eid)

    task = get_task('gmail_ambiguous_inbox_cleanup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_ambiguous_inbox_cleanup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_label_not_created_fails():
    """Apply labels but don't create the label first — create check fails."""
    _, _, targets, initial, state = _setup_session()
    # Only star deadline emails; skip label creation and newsletter archiving
    for eid in targets["deadline_email_ids"]:
        state.toggle_star(eid, is_starred=True)

    task = get_task('gmail_ambiguous_inbox_cleanup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "partial work should fail"
