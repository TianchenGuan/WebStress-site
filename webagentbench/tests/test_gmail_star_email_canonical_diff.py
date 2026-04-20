"""End-to-end tests for gmail_star_email canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_star_email',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Star the target email — score=1.0, passed=True."""
    sm, sid, targets, initial, state = _setup_session()
    state.toggle_star(targets["target_email_id"], is_starred=True)

    task = get_task('gmail_star_email')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — no positive action taken, score=0, passed=False (Class 1 guard)."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_star_email')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0, f"do-nothing score should be 0.0, got {report.score}"


def test_wrong_email_starred_fails():
    """Star a non-target email instead — wrong identity, passed=False."""
    _, _, targets, initial, state = _setup_session()
    wrong_id = next(e.id for e in state.emails if e.id != targets["target_email_id"])
    state.toggle_star(wrong_id, is_starred=True)

    task = get_task('gmail_star_email')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "starring wrong email should fail"


def test_excess_star_fails():
    """Star the target email plus one extra — invariant violation, passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.toggle_star(targets["target_email_id"], is_starred=True)
    extra_id = next(e.id for e in state.emails if e.id != targets["target_email_id"])
    state.toggle_star(extra_id, is_starred=True)

    task = get_task('gmail_star_email')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "excess star should trigger invariant violation"
