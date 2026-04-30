"""End-to-end tests for gmail_invoice_dispute_reversal canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_invoice_dispute_reversal',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Rejection reply to Hawthorne (over limit)
    state.send_email(
        subject="Re: Invoice",
        body="This invoice exceeds our processing limit and is rejected.",
        to=[state.get_email(targets["hawthorne_email_id"]).from_addr],
        in_reply_to=targets["hawthorne_email_id"],
    )
    # Rejection reply to Ridgeline (over limit, no exception)
    state.send_email(
        subject="Re: Invoice",
        body="This invoice exceeds our processing limit and is rejected.",
        to=[state.get_email(targets["ridgeline_email_id"]).from_addr],
        in_reply_to=targets["ridgeline_email_id"],
    )
    # Correction to Hawthorne (CFO approved exception)
    state.send_email(
        subject="Re: Invoice",
        body=(
            f"Please disregard our previous rejection. "
            f"Invoice #{targets['approved_invoice_number']} has been approved under a one-time exception."
        ),
        to=[state.get_email(targets["hawthorne_email_id"]).from_addr],
        in_reply_to=targets["hawthorne_email_id"],
    )
    # Confirmation to CFO
    state.send_email(
        subject="Re: Exception Approval",
        body=(
            f"Exception applied for {targets['approved_vendor_name']} "
            f"invoice #{targets['approved_invoice_number']}."
        ),
        to=[state.get_email(targets["cfo_approval_email_id"]).from_addr],
        in_reply_to=targets["cfo_approval_email_id"],
    )
    # Star CFO approval email
    state.toggle_star(targets["cfo_approval_email_id"], is_starred=True)


def test_correct_trajectory_passes():
    """All invoice replies and corrections sent, CFO email starred — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_invoice_dispute_reversal')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_invoice_dispute_reversal')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_correction_to_hawthorne_fails():
    """Send rejections but skip the correction to Hawthorne — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Only send initial rejections, skip correction
    state.send_email(
        subject="Re: Invoice",
        body="This invoice exceeds our processing limit and is rejected.",
        to=[state.get_email(targets["hawthorne_email_id"]).from_addr],
        in_reply_to=targets["hawthorne_email_id"],
    )
    state.send_email(
        subject="Re: Invoice",
        body="This invoice exceeds our processing limit and is rejected.",
        to=[state.get_email(targets["ridgeline_email_id"]).from_addr],
        in_reply_to=targets["ridgeline_email_id"],
    )
    # Skip correction to Hawthorne
    state.send_email(
        subject="Re: Exception",
        body=f"Exception applied for {targets['approved_vendor_name']}.",
        to=[state.get_email(targets["cfo_approval_email_id"]).from_addr],
        in_reply_to=targets["cfo_approval_email_id"],
    )
    state.toggle_star(targets["cfo_approval_email_id"], is_starred=True)

    task = get_task('gmail_invoice_dispute_reversal')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing correction to Hawthorne should fail"
