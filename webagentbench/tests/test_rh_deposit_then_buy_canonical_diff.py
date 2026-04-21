"""End-to-end tests for rh_deposit_then_buy canonical_diff.

Task: "Deposit $2,000 from your Chase checking account, then buy $1,500
worth of VTI at market price."

Verifies:
  - Correct trajectory (deposit $2k + buy VTI) passes with score 1.0.
  - Wrong deposit amount fails.
  - No buy order (deposit only) fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_deposit_then_buy",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    bank_id = state.linked_banks[0].id
    state.initiate_transfer("deposit", Decimal("2000"), bank_id)
    vti_price = state.get_stock("VTI").price
    quantity = int(Decimal("1500") / vti_price)
    state.place_order(
        symbol="VTI",
        side="buy",
        order_type="market",
        quantity=Decimal(max(quantity, 1)),
    )

    task = get_task("rh_deposit_then_buy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_deposit_amount_fails():
    """Agent deposits $1,000 instead of $2,000."""
    sm, sid, targets, initial, state = _setup_session()
    bank_id = state.linked_banks[0].id
    state.initiate_transfer("deposit", Decimal("1000"), bank_id)
    vti_price = state.get_stock("VTI").price
    state.place_order(
        symbol="VTI",
        side="buy",
        order_type="market",
        quantity=Decimal(max(int(Decimal("1500") / vti_price), 1)),
    )

    task = get_task("rh_deposit_then_buy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "wrong deposit amount should fail — transfer amount eq predicate requires $2000"
    )


def test_no_buy_order_fails():
    """Agent deposits correctly but never buys VTI."""
    sm, sid, targets, initial, state = _setup_session()
    bank_id = state.linked_banks[0].id
    state.initiate_transfer("deposit", Decimal("2000"), bank_id)

    task = get_task("rh_deposit_then_buy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "depositing without buying should fail — order create entry not matched"
    )
