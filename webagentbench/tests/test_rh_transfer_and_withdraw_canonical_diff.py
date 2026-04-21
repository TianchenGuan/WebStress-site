"""End-to-end tests for rh_transfer_and_withdraw canonical_diff.

Task: Check cash balance ($5,000), then withdraw half ($2,500) to Wells Fargo savings.

Verifies:
  - Withdrawing exactly $2,500 passes.
  - Withdrawing wrong amount fails.
  - Making a deposit instead of withdrawal fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_transfer_and_withdraw",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _get_bank_id(state):
    return state.linked_banks[0].id


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    cash = state.cash_balance
    state.initiate_transfer(direction="withdrawal", amount=cash / 2, bank_account_id=_get_bank_id(state))

    task = get_task("rh_transfer_and_withdraw")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_amount_fails():
    """Agent withdraws a different amount."""
    sm, sid, targets, initial, state = _setup_session()
    state.initiate_transfer(direction="withdrawal", amount=Decimal("1000"), bank_account_id=_get_bank_id(state))

    task = get_task("rh_transfer_and_withdraw")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wrong withdrawal amount should fail"


def test_deposit_instead_fails():
    """Agent makes a deposit instead of a withdrawal."""
    sm, sid, targets, initial, state = _setup_session()
    state.initiate_transfer(direction="deposit", amount=Decimal("2500"), bank_account_id=_get_bank_id(state))

    task = get_task("rh_transfer_and_withdraw")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "deposit instead of withdrawal should fail"
