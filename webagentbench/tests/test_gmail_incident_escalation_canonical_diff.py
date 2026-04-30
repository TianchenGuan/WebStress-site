"""End-to-end tests for gmail_incident_escalation canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_incident_escalation',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Forward alert to on-call engineer with error code
    state.forward_email(
        targets["alert_id"],
        to=[targets["oncall_email"]],
        body=f"Please investigate. Error code: {targets['error_code']}",
    )
    # Reply to manager thread confirming handling
    state.send_email(
        subject="Re: Incident",
        body="I am handling the incident now.",
        to=[state.get_email(targets["manager_email_id"]).from_addr],
        in_reply_to=targets["manager_email_id"],
    )
    # Create P0 Incident label
    state.ensure_label("P0 Incident")
    # Create filter for alert system with CRITICAL subject keyword
    state.create_filter(FilterRule(
        id='f_p0',
        name='p0 incident filter',
        from_addresses=[targets["alert_system_email"]],
        subject_keywords=['CRITICAL'],
        star=True,
        add_labels=['P0 Incident'],
    ))
    # Star and label all incident-related emails
    for eid in targets["incident_ids"]:
        state.toggle_star(eid, is_starred=True)
        state.apply_label(eid, "P0 Incident", action='add')


def test_correct_trajectory_passes():
    """All incident escalation steps completed — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_incident_escalation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_incident_escalation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_error_code_in_forward_fails():
    """Forward alert without error code — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Forward without including error code
    state.forward_email(
        targets["alert_id"],
        to=[targets["oncall_email"]],
        body="Please investigate this alert.",  # missing error code
    )
    state.send_email(
        subject="Re: Incident",
        body="I am handling it.",
        to=[state.get_email(targets["manager_email_id"]).from_addr],
        in_reply_to=targets["manager_email_id"],
    )
    state.ensure_label("P0 Incident")
    state.create_filter(FilterRule(
        id='f_p0',
        name='p0 incident filter',
        from_addresses=[targets["alert_system_email"]],
        subject_keywords=['CRITICAL'],
        star=True,
        add_labels=['P0 Incident'],
    ))
    for eid in targets["incident_ids"]:
        state.toggle_star(eid, is_starred=True)
        state.apply_label(eid, "P0 Incident", action='add')

    task = get_task('gmail_incident_escalation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing error code in forward should fail"


def test_manager_reply_all_fails():
    """The manager status reply must be reply-only."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)
    manager_reply = next(sent for sent in state.sent if sent.in_reply_to == targets["manager_email_id"])
    manager_reply.cc = ["leadership@example.com"]
    state.touch()

    task = get_task('gmail_incident_escalation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "reply-all CC should fail"
