"""End-to-end tests for rh_setup_recurring_investment canonical_diff.

Task: "Set up a monthly $200 recurring investment into VOO starting next Monday."

Verifies:
  - Correct trajectory (monthly $200 VOO RI) passes with score 1.0.
  - Wrong symbol fails.
  - Wrong amount fails.
  - Wrong frequency fails.
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
        task_id="rh_setup_recurring_investment",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _next_monday():
    today = datetime.date.today()
    days_ahead = (0 - today.weekday() + 7) % 7 or 7
    return today + datetime.timedelta(days=days_ahead)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.create_recurring_investment("VOO", Decimal("200"), "monthly", _next_monday())

    task = get_task("rh_setup_recurring_investment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_symbol_fails():
    """Agent creates RI for SPY instead of VOO."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_recurring_investment("SPY", Decimal("200"), "monthly", _next_monday())

    task = get_task("rh_setup_recurring_investment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "wrong symbol should fail — symbol eq predicate requires VOO"
    )


def test_wrong_amount_fails():
    """Agent creates RI for $100 instead of $200."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_recurring_investment("VOO", Decimal("100"), "monthly", _next_monday())

    task = get_task("rh_setup_recurring_investment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "wrong amount should fail — amount eq predicate requires $200"
    )


def test_wrong_frequency_fails():
    """Agent creates weekly RI instead of monthly."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_recurring_investment("VOO", Decimal("200"), "weekly", _next_monday())

    task = get_task("rh_setup_recurring_investment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "wrong frequency should fail — frequency eq predicate requires monthly"
    )
