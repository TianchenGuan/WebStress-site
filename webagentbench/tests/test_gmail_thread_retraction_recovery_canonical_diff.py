"""End-to-end tests for gmail_thread_retraction_recovery canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_thread_retraction_recovery',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Forward Yvonne's decision message to Ravi Menon
    state.send_email(
        subject="Atlas decision",
        body="Forwarding the final decision on Project Atlas.",
        to=[targets["ravi_menon_email"]],
        forwarded_from_id=targets["atlas_msg_4_id"],
    )
    # Send correction email
    state.send_email(
        subject="CORRECTION: Atlas decision",
        body=(
            "Please disregard my previous forward. The decision has been reversed. "
            "The correct decision is Option A, not Option B."
        ),
        to=[targets["ravi_menon_email"]],
    )


def test_correct_trajectory_passes():
    """Forward and then correct — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_thread_retraction_recovery')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_thread_retraction_recovery')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_correction_fails():
    """Send only the initial forward, no correction email — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Atlas decision",
        body="Forwarding the final decision on Project Atlas.",
        to=[targets["ravi_menon_email"]],
        forwarded_from_id=targets["atlas_msg_4_id"],
    )
    # Skip correction

    task = get_task('gmail_thread_retraction_recovery')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing correction should fail"
