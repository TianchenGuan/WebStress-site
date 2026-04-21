"""End-to-end tests for rh_sell_shares canonical_diff.

Task: "Sell all of your {target.symbol} shares." (target: TSLA, quantity: 5)

Verifies:
  - Correct trajectory (sell all 5 TSLA) passes with score 1.0.
  - Wrong symbol sold fails.
  - Partial sell fails (position not deleted, mismatches delete entry).
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_sell_shares",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.place_order(
        symbol=targets["symbol"],
        side="sell",
        order_type="market",
        quantity=Decimal(str(targets["quantity"])),
    )

    task = get_task("rh_sell_shares")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_symbol_fails():
    """Agent sells AAPL instead of TSLA."""
    sm, sid, targets, initial, state = _setup_session()
    aapl_pos = next(p for p in state.positions if p.symbol == "AAPL")
    state.place_order(
        symbol="AAPL",
        side="sell",
        order_type="market",
        quantity=aapl_pos.quantity,
    )

    task = get_task("rh_sell_shares")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "selling AAPL instead of TSLA should fail — symbol expr predicate rejects it"
    )


def test_partial_sell_fails():
    """Agent sells only 2 of 5 TSLA shares (position not fully liquidated)."""
    sm, sid, targets, initial, state = _setup_session()
    state.place_order(
        symbol=targets["symbol"],
        side="sell",
        order_type="market",
        quantity=Decimal("2"),
    )

    task = get_task("rh_sell_shares")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "partial sell should fail — order quantity predicate requires full quantity, "
        "and delete entry expects position to be removed"
    )
