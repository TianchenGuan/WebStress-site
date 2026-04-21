"""End-to-end tests for rh_complete_account_audit canonical_diff.

Task: (1) Create "Discrepancy Review" watchlist with mismatch symbol,
(2) delete stale price alerts, (3) delete overdue recurring investments,
(4) mark all notifications as read.

Verifies:
  - Correct full trajectory passes.
  - Missing one action (no watchlist created) fails.
  - Skipping notification read-marking fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_complete_account_audit",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_full_audit(state, targets):
    """Perform all four audit actions."""
    mismatch = targets["mismatch_symbol"]
    state.create_watchlist("Discrepancy Review", [mismatch])

    for alert in list(state.price_alerts):
        if not alert.id.startswith("alert_decoy_") and alert.symbol not in state.owned_symbols():
            state.delete_price_alert(alert.id)

    for ri in list(state.recurring_investments):
        if not ri.id.startswith("ri_decoy_") and ri in state.overdue_recurring_investments():
            state.delete_recurring_investment(ri.id)

    for notif in state.notifications:
        if not notif.is_read:
            state.mark_notification_read(notif.id)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_full_audit(state, targets)

    task = get_task("rh_complete_account_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_watchlist_fails():
    """Agent does everything except create the Discrepancy Review watchlist."""
    sm, sid, targets, initial, state = _setup_session()

    for alert in list(state.price_alerts):
        if not alert.id.startswith("alert_decoy_") and alert.symbol not in state.owned_symbols():
            state.delete_price_alert(alert.id)

    for ri in list(state.recurring_investments):
        if not ri.id.startswith("ri_decoy_") and ri in state.overdue_recurring_investments():
            state.delete_recurring_investment(ri.id)

    for notif in state.notifications:
        if not notif.is_read:
            state.mark_notification_read(notif.id)

    task = get_task("rh_complete_account_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing Discrepancy Review watchlist should fail"


def test_unread_notifications_fails():
    """Agent does everything except mark notifications as read."""
    sm, sid, targets, initial, state = _setup_session()
    mismatch = targets["mismatch_symbol"]
    state.create_watchlist("Discrepancy Review", [mismatch])

    for alert in list(state.price_alerts):
        if not alert.id.startswith("alert_decoy_") and alert.symbol not in state.owned_symbols():
            state.delete_price_alert(alert.id)

    for ri in list(state.recurring_investments):
        if not ri.id.startswith("ri_decoy_") and ri in state.overdue_recurring_investments():
            state.delete_recurring_investment(ri.id)

    # Intentionally skip marking notifications as read

    task = get_task("rh_complete_account_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "unread notifications remaining should fail"
