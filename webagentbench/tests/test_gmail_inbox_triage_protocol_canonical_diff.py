"""End-to-end tests for gmail_inbox_triage_protocol canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_inbox_triage_protocol',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Forward security alert to escalation email
    state.forward_email(
        targets["security_email_id"],
        to=[targets["escalation_email"]],
    )
    # Reply to onboarding email with confirmation phrase
    state.send_email(
        subject="Re: Onboarding Checklist",
        body=targets["confirmation_phrase"],
        to=[],
        in_reply_to=targets["onboarding_email_id"],
    )
    # Star and label Finance Review on invoice email
    state.ensure_label("Finance Review")
    state.toggle_star(targets["invoice_email_id"], is_starred=True)
    state.apply_label(targets["invoice_email_id"], "Finance Review", action='add')
    # Archive promotional offer
    state.archive_email(targets["promo_email_id"])
    # Apply Travel Follow-up label to travel request
    state.ensure_label("Travel Follow-up")
    state.apply_label(targets["travel_email_id"], "Travel Follow-up", action='add')


def test_correct_trajectory_passes():
    """All triage actions completed — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_inbox_triage_protocol')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_inbox_triage_protocol')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_forward_wrong_security_email_fails():
    """Forward security follow-up (resolved) instead of original alert — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Forward wrong security email (the follow-up saying it was resolved)
    state.forward_email(
        targets["security_followup_email_id"],  # wrong - follow-up not original
        to=[targets["escalation_email"]],
    )
    state.send_email(
        subject="Re: Onboarding",
        body=targets["confirmation_phrase"],
        to=[],
        in_reply_to=targets["onboarding_email_id"],
    )
    state.ensure_label("Finance Review")
    state.toggle_star(targets["invoice_email_id"], is_starred=True)
    state.apply_label(targets["invoice_email_id"], "Finance Review", action='add')
    state.archive_email(targets["promo_email_id"])
    state.ensure_label("Travel Follow-up")
    state.apply_label(targets["travel_email_id"], "Travel Follow-up", action='add')

    task = get_task('gmail_inbox_triage_protocol')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "forwarding wrong security email should fail"
