"""End-to-end tests for gmail_thread_deadline_cascade canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_thread_deadline_cascade',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Compose notification to project sponsor
    state.send_email(
        subject="Helios deadline cascade",
        body=(
            "The following deliverables are at risk due to the API Integration delay:\n\n"
            "QA Sign-off: original due date 2026-03-14\n"
            "Staging Deploy: original due date 2026-03-18\n"
            "Launch Readiness: original due date 2026-03-22"
        ),
        to=[targets["sponsor_email"]],
    )
    # Star one email in each at-risk thread
    qa_email = next(e for e in state.emails if e.thread_id == targets["qa_thread_id"])
    staging_email = next(e for e in state.emails if e.thread_id == targets["staging_thread_id"])
    launch_email = next(e for e in state.emails if e.thread_id == targets["launch_thread_id"])
    state.toggle_star(qa_email.id, is_starred=True)
    state.toggle_star(staging_email.id, is_starred=True)
    state.toggle_star(launch_email.id, is_starred=True)
    # Archive slip notification
    state.archive_email(targets["slip_notification_id"])


def test_correct_trajectory_passes():
    """Apply all deadline cascade actions — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_thread_deadline_cascade')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_thread_deadline_cascade')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_subject_fails():
    """Send email with wrong subject — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Helios update",  # wrong subject
        body=(
            "QA Sign-off: 2026-03-14\n"
            "Staging Deploy: 2026-03-18\n"
            "Launch Readiness: 2026-03-22"
        ),
        to=[targets["sponsor_email"]],
    )
    qa_email = next(e for e in state.emails if e.thread_id == targets["qa_thread_id"])
    staging_email = next(e for e in state.emails if e.thread_id == targets["staging_thread_id"])
    launch_email = next(e for e in state.emails if e.thread_id == targets["launch_thread_id"])
    state.toggle_star(qa_email.id, is_starred=True)
    state.toggle_star(staging_email.id, is_starred=True)
    state.toggle_star(launch_email.id, is_starred=True)
    state.archive_email(targets["slip_notification_id"])

    task = get_task('gmail_thread_deadline_cascade')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong subject should fail"
