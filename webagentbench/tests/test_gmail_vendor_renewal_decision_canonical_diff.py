"""End-to-end tests for gmail_vendor_renewal_decision canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_vendor_renewal_decision',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Compose recommendation email to procurement
    state.send_email(
        subject="Q2 Renewal Recommendation",
        body=(
            f"Recommend renewing {targets['qualifying_vendor_name']} at "
            f"{targets['qualifying_vendor_cost']}/year with {targets['qualifying_vendor_sla']} SLA."
        ),
        to=["procurement@company.com"],
    )
    # Forward qualifying vendor proposal to legal
    state.forward_email(
        targets["qualifying_vendor_email_id"],
        to=["legal@company.com"],
        body="Please review the attached renewal for contract processing.",
    )
    # Star the qualifying vendor proposal
    state.toggle_star(targets["qualifying_vendor_email_id"], is_starred=True)
    # Archive non-qualifying vendor proposals
    for eid in targets["non_qualifying_email_ids"]:
        state.archive_email(eid)


def test_correct_trajectory_passes():
    """Apply all vendor renewal decision actions — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_vendor_renewal_decision')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_vendor_renewal_decision')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_vendor_forwarded_fails():
    """Forward non-qualifying proposal to legal — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Q2 Renewal Recommendation",
        body=(
            f"Recommend renewing {targets['qualifying_vendor_name']} at "
            f"{targets['qualifying_vendor_cost']}/year with {targets['qualifying_vendor_sla']} SLA."
        ),
        to=["procurement@company.com"],
    )
    # Forward wrong vendor to legal
    state.forward_email(
        targets["non_qualifying_email_ids"][0],  # wrong vendor
        to=["legal@company.com"],
        body="Please review the attached renewal for contract processing.",
    )
    state.toggle_star(targets["qualifying_vendor_email_id"], is_starred=True)
    for eid in targets["non_qualifying_email_ids"]:
        state.archive_email(eid)

    task = get_task('gmail_vendor_renewal_decision')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "forwarding wrong vendor should fail"


def test_recommendation_extra_text_fails():
    """The procurement recommendation body is specified exactly."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)
    state.sent[0].body += " Extra note."

    task = get_task('gmail_vendor_renewal_decision')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "extra recommendation text should fail"
