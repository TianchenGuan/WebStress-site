"""End-to-end tests for gmail_delegation_handoff canonical_diff."""

from webagentbench.backend.models.gmail import Contact, FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_delegation_handoff',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    """Apply all handoff checklist mutations."""
    # Create On Leave label
    state.ensure_label("On Leave")
    # Create filter for vendor/partner contacts
    state.create_filter(FilterRule(
        id='f_leave', name='on leave filter',
        from_addresses=['cora.banks@vendor.io', 'lee.chang@vendor.io', 'ravi.gupta@partner.com'],
        add_labels=['On Leave'], star=True,
    ))
    # Forward 3 threads to delegate
    state.forward_email(targets["vendor_email_id"], to=["delegate@company.io"])
    state.forward_email(targets["partner_email_id"], to=["delegate@company.io"])
    state.forward_email(targets["budget_email_id"], to=["delegate@company.io"])
    # Reply to Sprint 14 Blockers
    state.send_email(
        subject="Re: Sprint 14 Blockers",
        body="Status: blocked on API credentials. ETA next Wednesday.",
        to=["team@company.io"],
        in_reply_to=targets["sprint_email_id"],
        thread_id="thread_sprint",
    )
    # Reply to Design Review Mobile Nav
    state.send_email(
        subject="Re: Design Review Feedback - Mobile Nav",
        body="Status: feedback incorporated, PR submitted.",
        to=["design@company.io"],
        in_reply_to=targets["design_nav_email_id"],
        thread_id="thread_design_nav",
    )
    # Add delegate contact
    state.add_contact(Contact(id='c_delegate', name='Jamie Park',
                              email='delegate@company.io'))


def test_correct_trajectory_passes():
    """Complete the delegation handoff checklist — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_delegation_handoff')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_delegation_handoff')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_reply_text_fails():
    """Reply to Sprint with wrong text — body check fails."""
    _, _, targets, initial, state = _setup_session()
    state.ensure_label("On Leave")
    state.create_filter(FilterRule(
        id='f_leave2', name='on leave filter',
        from_addresses=['cora.banks@vendor.io', 'lee.chang@vendor.io', 'ravi.gupta@partner.com'],
        add_labels=['On Leave'], star=True,
    ))
    state.forward_email(targets["vendor_email_id"], to=["delegate@company.io"])
    state.forward_email(targets["partner_email_id"], to=["delegate@company.io"])
    state.forward_email(targets["budget_email_id"], to=["delegate@company.io"])
    state.send_email(
        subject="Re: Sprint 14 Blockers",
        body="Everything is going well.",  # wrong reply text
        to=["team@company.io"],
        in_reply_to=targets["sprint_email_id"],
        thread_id="thread_sprint",
    )
    state.send_email(
        subject="Re: Design Review Feedback - Mobile Nav",
        body="Status: feedback incorporated, PR submitted.",
        to=["design@company.io"],
        in_reply_to=targets["design_nav_email_id"],
        thread_id="thread_design_nav",
    )
    state.add_contact(Contact(id='c_del2', name='Jamie Park', email='delegate@company.io'))

    task = get_task('gmail_delegation_handoff')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong reply text should fail"
