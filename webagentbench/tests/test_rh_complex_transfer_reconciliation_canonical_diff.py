"""End-to-end tests for rh_complex_transfer_reconciliation canonical_diff.

Task: (1) Delete stale price alerts, (2) remove empty watchlists,
(3) delete overdue recurring investments, (4) deposit $2,500 from default bank.

Verifies:
  - Correct full trajectory passes.
  - Wrong deposit amount fails.
  - Skipping stale alert cleanup fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_complex_transfer_reconciliation",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_full_cleanup(state):
    """Perform all four cleanup actions."""
    for alert in list(state.price_alerts):
        if not alert.id.startswith("alert_decoy_") and alert.symbol not in state.owned_symbols():
            state.delete_price_alert(alert.id)

    for wl in list(state.watchlists):
        if len(wl.symbols) == 0:
            state.delete_watchlist(wl.id)

    for ri in list(state.recurring_investments):
        if not ri.id.startswith("ri_decoy_") and ri in state.overdue_recurring_investments():
            state.delete_recurring_investment(ri.id)

    bank = state.linked_banks[0]
    state.initiate_transfer("deposit", Decimal("2500"), bank.id)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_full_cleanup(state)

    task = get_task("rh_complex_transfer_reconciliation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_deposit_amount_fails():
    """Agent deposits wrong amount ($1,000 instead of $2,500)."""
    sm, sid, targets, initial, state = _setup_session()

    for alert in list(state.price_alerts):
        if not alert.id.startswith("alert_decoy_") and alert.symbol not in state.owned_symbols():
            state.delete_price_alert(alert.id)

    for wl in list(state.watchlists):
        if len(wl.symbols) == 0:
            state.delete_watchlist(wl.id)

    for ri in list(state.recurring_investments):
        if not ri.id.startswith("ri_decoy_") and ri in state.overdue_recurring_investments():
            state.delete_recurring_investment(ri.id)

    bank = state.linked_banks[0]
    state.initiate_transfer("deposit", Decimal("1000"), bank.id)  # wrong amount

    task = get_task("rh_complex_transfer_reconciliation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wrong deposit amount should fail"


def test_stale_alerts_not_removed_fails():
    """Agent skips removing stale price alerts."""
    sm, sid, targets, initial, state = _setup_session()
    stale_count = len([a for a in state.price_alerts
                       if not a.id.startswith("alert_decoy_") and a.symbol not in state.owned_symbols()])
    assert stale_count >= 1, "seed must have stale alerts"

    for wl in list(state.watchlists):
        if len(wl.symbols) == 0:
            state.delete_watchlist(wl.id)

    for ri in list(state.recurring_investments):
        if not ri.id.startswith("ri_decoy_") and ri in state.overdue_recurring_investments():
            state.delete_recurring_investment(ri.id)

    bank = state.linked_banks[0]
    state.initiate_transfer("deposit", Decimal("2500"), bank.id)

    task = get_task("rh_complex_transfer_reconciliation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "remaining stale alerts should fail"
