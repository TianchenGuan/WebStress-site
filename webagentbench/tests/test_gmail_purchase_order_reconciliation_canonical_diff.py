"""End-to-end tests for gmail_purchase_order_reconciliation canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_purchase_order_reconciliation',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Compose reconciliation email to CFO
    state.send_email(
        subject="Q1 PO-Invoice Reconciliation",
        body=(
            f"Q1 PO-Invoice Reconciliation Report:\n\n"
            f"PO {targets['po_number_1']}: "
            f"Approved {targets['approved_1']}, Billed {targets['billed_1']}, "
            f"Discrepancy {targets['discrepancy_1']}\n"
            f"PO {targets['po_number_2']}: "
            f"Approved {targets['approved_2']}, Billed {targets['billed_2']}, "
            f"Discrepancy {targets['discrepancy_2']}\n"
            f"PO {targets['po_number_3']}: "
            f"Approved {targets['approved_3']}, Billed {targets['billed_3']}, "
            f"Discrepancy {targets['discrepancy_3']}\n"
        ),
        to=["cfo@company.com"],
    )
    # Star all three invoice emails
    for eid in targets["invoice_email_ids"]:
        state.toggle_star(eid, is_starred=True)


def test_correct_trajectory_passes():
    """Reconciliation email sent to CFO and invoice emails starred — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_purchase_order_reconciliation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_purchase_order_reconciliation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_discrepancy_fails():
    """Send reconciliation email but omit one discrepancy value — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Include po_number_1 and po_number_2 but omit po_number_3 and discrepancy_3
    state.send_email(
        subject="Q1 PO-Invoice Reconciliation",
        body=(
            f"PO {targets['po_number_1']}: Discrepancy {targets['discrepancy_1']}\n"
            f"PO {targets['po_number_2']}: Discrepancy {targets['discrepancy_2']}\n"
            # Missing po_number_3 and discrepancy_3
        ),
        to=["cfo@company.com"],
    )
    for eid in targets["invoice_email_ids"]:
        state.toggle_star(eid, is_starred=True)

    task = get_task('gmail_purchase_order_reconciliation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing discrepancy should fail"
