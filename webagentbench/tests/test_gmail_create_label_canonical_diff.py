"""End-to-end tests for gmail_create_label canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_create_label',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Create the 'Important Projects' label — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    state.ensure_label("Important Projects", color="#1a73e8")

    task = get_task('gmail_create_label')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False (Class 1 guard)."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_create_label')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_label_name_fails():
    """Create a label with the wrong name — identity check fails, passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.ensure_label("Important Stuff")  # wrong name

    task = get_task('gmail_create_label')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong label name should fail"


def test_excess_label_fails():
    """Create 'Important Projects' plus an extra label — invariant violation."""
    _, _, targets, initial, state = _setup_session()
    state.ensure_label("Important Projects")
    state.ensure_label("Extra Label")

    task = get_task('gmail_create_label')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "excess label creation should trigger invariant violation"
