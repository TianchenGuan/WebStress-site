"""End-to-end tests for rh_consolidate_recurring canonical_diff.

Task: Find duplicate recurring investments (AAPL, MSFT each have 2), consolidate
each into a single monthly investment with the combined amount.

Verifies:
  - Correct trajectory (delete duplicates + create consolidated monthly) passes.
  - Wrong frequency (keeping weekly instead of switching to monthly) fails.
  - Missing combined amount fails.
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
        task_id="rh_consolidate_recurring",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    duplicate_syms = targets["duplicate_symbols"]
    combined = targets["combined_amounts"]

    # Delete all duplicate recurring investments
    for ri in list(state.recurring_investments):
        if ri.symbol in duplicate_syms and not ri.id.startswith("ri_decoy_"):
            state.delete_recurring_investment(ri.id)

    # Create one consolidated monthly recurring investment per duplicate symbol
    for sym in duplicate_syms:
        state.create_recurring_investment(
            symbol=sym,
            amount=Decimal(combined[sym]),
            frequency="monthly",
            next_execution_date=datetime.date.today() + datetime.timedelta(days=30),
        )

    task = get_task("rh_consolidate_recurring")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_frequency_fails():
    """Agent consolidates but uses 'weekly' instead of 'monthly'."""
    sm, sid, targets, initial, state = _setup_session()
    duplicate_syms = targets["duplicate_symbols"]
    combined = targets["combined_amounts"]

    for ri in list(state.recurring_investments):
        if ri.symbol in duplicate_syms and not ri.id.startswith("ri_decoy_"):
            state.delete_recurring_investment(ri.id)

    for sym in duplicate_syms:
        state.create_recurring_investment(
            symbol=sym,
            amount=Decimal(combined[sym]),
            frequency="weekly",  # wrong: should be monthly
            next_execution_date=datetime.date.today() + datetime.timedelta(days=7),
        )

    task = get_task("rh_consolidate_recurring")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "weekly frequency instead of monthly should fail"


def test_wrong_amount_fails():
    """Agent creates consolidated but with wrong (not combined) amount."""
    sm, sid, targets, initial, state = _setup_session()
    duplicate_syms = targets["duplicate_symbols"]

    for ri in list(state.recurring_investments):
        if ri.symbol in duplicate_syms and not ri.id.startswith("ri_decoy_"):
            state.delete_recurring_investment(ri.id)

    for sym in duplicate_syms:
        state.create_recurring_investment(
            symbol=sym,
            amount=Decimal("100"),  # wrong: not the combined amount
            frequency="monthly",
            next_execution_date=datetime.date.today() + datetime.timedelta(days=30),
        )

    task = get_task("rh_consolidate_recurring")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wrong combined amount should fail"
