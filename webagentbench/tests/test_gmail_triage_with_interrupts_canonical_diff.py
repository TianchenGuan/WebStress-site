"""End-to-end tests for gmail_triage_with_interrupts canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_triage_with_interrupts',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Star all client emails
    for eid in targets["client_ids"]:
        state.toggle_star(eid, is_starred=True)
    # Archive all newsletter emails
    for eid in targets["newsletter_ids"]:
        state.archive_email(eid)
    # Forward each escalation email to team lead
    for eid in targets["escalation_ids"]:
        state.forward_email(eid, to=[targets["team_lead_email"]])
    # Star boss email
    state.toggle_star(targets["boss_email_id"], is_starred=True)


def test_correct_trajectory_passes():
    """Apply all triage rules — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_triage_with_interrupts')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_triage_with_interrupts')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_escalation_forward_fails():
    """Apply all rules except forwarding escalations — should fail."""
    _, _, targets, initial, state = _setup_session()
    for eid in targets["client_ids"]:
        state.toggle_star(eid, is_starred=True)
    for eid in targets["newsletter_ids"]:
        state.archive_email(eid)
    # Skip escalation forwards
    state.toggle_star(targets["boss_email_id"], is_starred=True)

    task = get_task('gmail_triage_with_interrupts')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing escalation forwards should fail"
