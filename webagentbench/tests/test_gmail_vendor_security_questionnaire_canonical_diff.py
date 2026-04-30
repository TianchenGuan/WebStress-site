"""End-to-end tests for gmail_vendor_security_questionnaire canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_vendor_security_questionnaire',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Reply to vendor questionnaire with all 8 answers and CCs
    state.send_email(
        subject="Re: Security Questionnaire: Acme Corp Onboarding",
        body=(
            f"Q1: {targets['q1_answer']}\n"
            f"Q2: {targets['q2_answer']}\n"
            f"Q3: {targets['q3_answer']}\n"
            f"Q4: {targets['q4_answer']}\n"
            f"Q5: {targets['q5_correct']}\n"
            f"Q6: {targets['q6_answer']}\n"
            f"Q7: {targets['q7_answer']}\n"
            f"Q8: {targets['q8_correct']}"
        ),
        to=[state.get_email(targets["vendor_email_id"]).from_addr],
        cc=targets["cc_addresses"],
        in_reply_to=targets["vendor_email_id"],
    )
    # Forward vendor questionnaire to coordinator
    state.forward_email(
        targets["vendor_email_id"],
        to=[targets["forward_to"]],
        body="All 8 answers submitted. See reply thread.",
    )
    # Star all 6 internal source emails
    for eid in targets["internal_email_ids"]:
        state.toggle_star(eid, is_starred=True)
    # Update contact notes
    dana_contact = next(c for c in state.contacts if c.email == targets["dana_park_email"])
    frank_contact = next(c for c in state.contacts if c.email == targets["frank_osei_email"])
    grace_contact = next(c for c in state.contacts if c.email == targets["grace_liu_email"])
    state.update_contact(dana_contact.id, note=targets["dana_note"])
    state.update_contact(frank_contact.id, note=targets["frank_note"])
    state.update_contact(grace_contact.id, note=targets["grace_note"])


def test_correct_trajectory_passes():
    """Apply all security questionnaire actions — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_vendor_security_questionnaire')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_vendor_security_questionnaire')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_q5_answer_fails():
    """Use wrong (outdated) Q5 answer — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Security Questionnaire: Acme Corp Onboarding",
        body=(
            f"Q1: {targets['q1_answer']}\n"
            f"Q2: {targets['q2_answer']}\n"
            f"Q3: {targets['q3_answer']}\n"
            f"Q4: {targets['q4_answer']}\n"
            f"Q5: {targets['q5_wrong']}\n"  # wrong Q5
            f"Q6: {targets['q6_answer']}\n"
            f"Q7: {targets['q7_answer']}\n"
            f"Q8: {targets['q8_correct']}"
        ),
        to=[state.get_email(targets["vendor_email_id"]).from_addr],
        cc=targets["cc_addresses"],
        in_reply_to=targets["vendor_email_id"],
    )
    state.forward_email(
        targets["vendor_email_id"],
        to=[targets["forward_to"]],
        body="All 8 answers submitted. See reply thread.",
    )
    for eid in targets["internal_email_ids"]:
        state.toggle_star(eid, is_starred=True)
    dana_contact = next(c for c in state.contacts if c.email == targets["dana_park_email"])
    frank_contact = next(c for c in state.contacts if c.email == targets["frank_osei_email"])
    grace_contact = next(c for c in state.contacts if c.email == targets["grace_liu_email"])
    state.update_contact(dana_contact.id, note=targets["dana_note"])
    state.update_contact(frank_contact.id, note=targets["frank_note"])
    state.update_contact(grace_contact.id, note=targets["grace_note"])

    task = get_task('gmail_vendor_security_questionnaire')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong Q5 answer should fail"


def test_wrong_vendor_reply_recipient_fails():
    """The vendor questionnaire reply must go to the original sender, not the original TO."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)
    reply = next(sent for sent in state.sent if sent.in_reply_to == targets["vendor_email_id"])
    reply.to = ["procurement@cloudvault.io"]
    state.touch()

    task = get_task('gmail_vendor_security_questionnaire')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "replying to original TO instead of sender should fail"
