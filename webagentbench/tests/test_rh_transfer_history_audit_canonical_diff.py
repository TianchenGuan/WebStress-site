"""End-to-end tests for rh_transfer_history_audit canonical_diff.

Task: Review transfer history; if withdrawals exceed deposits, make a $3,000 deposit,
then set up a recurring weekly $200 VTI investment.

Verifies:
  - Correct full workflow (deposit + recurring RI) passes.
  - Missing $3,000 deposit (when required) fails.
  - Missing recurring VTI investment fails.
"""

from datetime import date
from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

_NEXT_DATE = date(2025, 7, 14)


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_transfer_history_audit",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _bank_id(state):
    return state.linked_banks[0].id


def _do_full_audit(state):
    """If withdrawals exceed deposits, deposit $3,000 then set up weekly $200 VTI RI."""
    if state.total_transferred("deposit") <= state.total_transferred("withdrawal"):
        state.initiate_transfer(direction="deposit", amount=Decimal("3000"), bank_account_id=_bank_id(state))
    state.create_recurring_investment(symbol="VTI", frequency="weekly", amount=Decimal("200"), next_execution_date=_NEXT_DATE)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_full_audit(state)

    task = get_task("rh_transfer_history_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_deposit_fails():
    """Agent skips the $3,000 deposit when withdrawals exceed deposits."""
    sm, sid, targets, initial, state = _setup_session()
    # Only set up RI, skip required deposit
    state.create_recurring_investment(symbol="VTI", frequency="weekly", amount=Decimal("200"), next_execution_date=_NEXT_DATE)

    task = get_task("rh_transfer_history_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing required deposit should fail"


def test_missing_recurring_investment_fails():
    """Agent makes the deposit but doesn't set up the recurring VTI investment."""
    sm, sid, targets, initial, state = _setup_session()
    state.initiate_transfer(direction="deposit", amount=Decimal("3000"), bank_account_id=_bank_id(state))
    # No recurring investment created

    task = get_task("rh_transfer_history_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing recurring investment should fail"
