"""End-to-end tests for rh_dividend_reinvestment_analysis canonical_diff.

Task: Disable dividend reinvestment for low-yield stocks; set up weekly $50
recurring investment in the highest yield-on-cost stock.

Verifies:
  - Correct trajectory (disable reinvest + create weekly RI) passes.
  - Wrong frequency (monthly instead of weekly) fails.
  - Wrong amount ($100 instead of $50) fails.
"""

import datetime
from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_dividend_reinvestment_analysis",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    best = targets["best_yield_symbol"]
    low_yields = targets["low_yield_symbols"]
    anchor = state.anchor_date()

    if low_yields:
        state.update_settings(reinvest_dividends=False)

    state.create_recurring_investment(
        symbol=best,
        amount=Decimal("50"),
        frequency="weekly",
        next_execution_date=anchor + datetime.timedelta(days=7),
    )

    task = get_task("rh_dividend_reinvestment_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_frequency_fails():
    """Agent creates monthly instead of weekly recurring investment."""
    sm, sid, targets, initial, state = _setup_session()
    best = targets["best_yield_symbol"]
    low_yields = targets["low_yield_symbols"]
    anchor = state.anchor_date()

    if low_yields:
        state.update_settings(reinvest_dividends=False)

    state.create_recurring_investment(
        symbol=best,
        amount=Decimal("50"),
        frequency="monthly",  # wrong
        next_execution_date=anchor + datetime.timedelta(days=30),
    )

    task = get_task("rh_dividend_reinvestment_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "monthly frequency instead of weekly should fail"


def test_wrong_amount_fails():
    """Agent creates weekly RI but with wrong amount ($100 instead of $50)."""
    sm, sid, targets, initial, state = _setup_session()
    best = targets["best_yield_symbol"]
    low_yields = targets["low_yield_symbols"]
    anchor = state.anchor_date()

    if low_yields:
        state.update_settings(reinvest_dividends=False)

    state.create_recurring_investment(
        symbol=best,
        amount=Decimal("100"),  # wrong: should be $50
        frequency="weekly",
        next_execution_date=anchor + datetime.timedelta(days=7),
    )

    task = get_task("rh_dividend_reinvestment_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "$100 instead of $50 should fail amount predicate"
