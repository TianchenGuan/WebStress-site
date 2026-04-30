"""End-to-end tests for gmail_thread_merge_conflict canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_thread_merge_conflict',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    state.send_email(
        subject="Conflict: Meridian Room double-booked for 2026-04-01",
        body=(
            f"Engineering decided: convert to server lab. "
            f"Decision by {targets['eng_decision_maker']} on {targets['eng_decision_date']}.\n\n"
            f"Executive decided: convert to executive lounge. "
            f"Decision by {targets['exec_decision_maker']} on {targets['exec_decision_date']}.\n\n"
            f"First decision: Engineering on {targets['eng_decision_date']}.\n\n"
            f"Recommended resolution: escalate to VP of Operations for final allocation."
        ),
        to=[targets["victor_hahn_email"], targets["leila_osman_email"],
            targets["nadia_orozco_email"]],
    )


def test_correct_trajectory_passes():
    """Compose conflict resolution email — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_thread_merge_conflict')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_thread_merge_conflict')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_recipient_fails():
    """Send email without all three required recipients — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Conflict: Meridian Room double-booked for 2026-04-01",
        body=(
            f"Engineering decided: convert to server lab. "
            f"Decision by {targets['eng_decision_maker']} on {targets['eng_decision_date']}.\n\n"
            f"Executive decided: convert to executive lounge. "
            f"Decision by {targets['exec_decision_maker']} on {targets['exec_decision_date']}.\n\n"
            f"First decision: Engineering on {targets['eng_decision_date']}.\n\n"
            f"Recommended resolution: escalate to VP of Operations for final allocation."
        ),
        to=[targets["victor_hahn_email"], targets["leila_osman_email"]],  # missing nadia
    )

    task = get_task('gmail_thread_merge_conflict')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing recipient should fail"


def test_extra_recipient_fails():
    """The conflict email must not include extra recipients beyond the three named recipients."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)
    state.sent[0].to.append("extra@example.com")
    state.touch()

    task = get_task('gmail_thread_merge_conflict')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "extra recipient should fail"
