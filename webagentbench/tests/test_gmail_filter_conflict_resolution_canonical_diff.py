"""End-to-end tests for gmail_filter_conflict_resolution canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_filter_conflict_resolution',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Delete both old filters, create 2 new non-overlapping filters and label — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.remove_filter(targets["old_filter_a_id"])
    state.remove_filter(targets["old_filter_b_id"])
    state.ensure_label("Analytics/Dashboard")
    state.create_filter(FilterRule(
        id='f_dashboard',
        name='dashboard filter',
        from_addresses=['reports@dataviz.io'],
        subject_keywords=['dashboard'],
        star=True,
        add_labels=['Analytics/Dashboard'],
    ))
    state.create_filter(FilterRule(
        id='f_export',
        name='export filter',
        from_addresses=['reports@dataviz.io'],
        subject_keywords=['export'],
        archive=True,
    ))

    task = get_task('gmail_filter_conflict_resolution')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_filter_conflict_resolution')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_old_filter_not_deleted_fails():
    """Only create new filters without deleting old ones — should fail."""
    _, _, targets, initial, state = _setup_session()
    # Don't delete old filters, just add new ones
    state.ensure_label("Analytics/Dashboard")
    state.create_filter(FilterRule(
        id='f_dashboard2',
        name='dashboard filter',
        from_addresses=['reports@dataviz.io'],
        subject_keywords=['dashboard'],
        star=True,
        add_labels=['Analytics/Dashboard'],
    ))

    task = get_task('gmail_filter_conflict_resolution')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "failing to delete old filters should fail"
