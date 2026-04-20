"""End-to-end tests for gmail_invoice_verification canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_invoice_verification',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Reply to mismatched vendor with correct PO number
    state.send_email(
        subject="Re: Invoice - PO Mismatch",
        body=(
            f"Please reissue the invoice with the correct PO number: "
            f"{targets['correct_po_for_mismatched']}."
        ),
        to=[targets["mismatched_vendor_email"]],
        in_reply_to=targets["mismatched_vendor_email_id"],
    )
    # Star the two valid invoice emails
    for eid in targets["valid_invoice_email_ids"]:
        state.toggle_star(eid, is_starred=True)


def test_correct_trajectory_passes():
    """Reply to mismatched vendor and star valid invoices — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_invoice_verification')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_invoice_verification')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_po_in_reply_fails():
    """Reply with wrong PO number — passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Invoice",
        body="Please reissue the invoice with the correct reference.",  # no PO number
        to=[targets["mismatched_vendor_email"]],
        in_reply_to=targets["mismatched_vendor_email_id"],
    )
    for eid in targets["valid_invoice_email_ids"]:
        state.toggle_star(eid, is_starred=True)

    task = get_task('gmail_invoice_verification')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong PO in reply should fail"
