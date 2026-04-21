"""End-to-end tests for rh_deposit_funds canonical_diff.

Task: "Deposit $500 from your default bank account."

Verifies:
  - Correct trajectory ($500 deposit) passes with score 1.0.
  - Wrong amount fails.
  - Withdrawal instead of deposit fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_deposit_funds",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    bank_id = targets["bank_ids"][0]
    state.initiate_transfer("deposit", Decimal("500"), bank_id)

    task = get_task("rh_deposit_funds")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_amount_fails():
    """Agent deposits $1000 instead of $500."""
    sm, sid, targets, initial, state = _setup_session()
    bank_id = targets["bank_ids"][0]
    state.initiate_transfer("deposit", Decimal("1000"), bank_id)

    task = get_task("rh_deposit_funds")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "depositing $1000 should fail — amount eq predicate requires exactly $500"
    )


def test_withdrawal_fails():
    """Agent makes a withdrawal instead of a deposit."""
    sm, sid, targets, initial, state = _setup_session()
    bank_id = targets["bank_ids"][0]
    state.initiate_transfer("withdrawal", Decimal("500"), bank_id)

    task = get_task("rh_deposit_funds")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "withdrawal instead of deposit should fail — direction eq predicate and no-withdrawal constraint"
    )
