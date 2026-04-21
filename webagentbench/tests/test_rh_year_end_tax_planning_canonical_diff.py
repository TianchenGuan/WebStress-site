"""End-to-end tests for rh_year_end_tax_planning canonical_diff.

Task: Sell loss positions (avoiding wash sales), then set up recurring re-entry investments.

Verifies:
  - Correct harvest + recurring RI setup passes.
  - Missing recurring investments fails.
  - Wash sale violation fails.
"""

from datetime import date
from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

_NEXT_DATE = date(2025, 8, 10)


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_year_end_tax_planning",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_full_plan(state, targets):
    eligible = [s for s in targets["loss_symbols"] if s not in targets["recent_buy_symbols"]]
    for sym in eligible:
        pos = state.get_position(sym)
        if pos and pos.quantity > 0:
            state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)
            state.create_recurring_investment(symbol=sym, frequency="monthly", amount=Decimal("100"), next_execution_date=_NEXT_DATE)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_full_plan(state, targets)

    task = get_task("rh_year_end_tax_planning")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_recurring_investment_fails():
    """Agent sells losses but doesn't set up re-entry recurring investments."""
    sm, sid, targets, initial, state = _setup_session()
    eligible = [s for s in targets["loss_symbols"] if s not in targets["recent_buy_symbols"]]
    for sym in eligible:
        pos = state.get_position(sym)
        if pos and pos.quantity > 0:
            state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)
    # No recurring investments

    task = get_task("rh_year_end_tax_planning")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing recurring investments should fail"


def test_wash_sale_violation_fails():
    """Agent sells a position that was purchased within the last 30 days."""
    sm, sid, targets, initial, state = _setup_session()
    recent = targets["recent_buy_symbols"]
    if recent:
        pos = state.get_position(recent[0])
        if pos and pos.quantity > 0:
            state.place_order(symbol=recent[0], side="sell", order_type="market", quantity=pos.quantity)
            state.create_recurring_investment(symbol=recent[0], frequency="monthly", amount=Decimal("100"), next_execution_date=_NEXT_DATE)

    task = get_task("rh_year_end_tax_planning")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wash sale violation should fail"
