"""End-to-end tests for rh_find_earnings_and_alert canonical_diff.

Task: "Find which stocks in your portfolio have earnings in the next 7 days.
For each, create a price alert set at 5% below their current price."

Verifies:
  - Correct trajectory (one alert per earnings stock at 95% price) passes.
  - Missing alert for one stock fails.
  - Alert for non-earnings stock fails.
"""

from decimal import Decimal

import pytest

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_find_earnings_and_alert",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    earnings_syms = state.portfolio_symbols_with_earnings_within(7)
    assert len(earnings_syms) >= 1, "seed must produce at least one portfolio stock with earnings"
    for sym in earnings_syms:
        price = state.get_stock(sym).price
        alert_price = (price * Decimal("0.95")).quantize(Decimal("0.01"))
        state.create_price_alert(sym, "below", alert_price)

    task = get_task("rh_find_earnings_and_alert")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_alert_fails():
    """Agent creates alerts for only some earnings stocks, misses one."""
    sm, sid, targets, initial, state = _setup_session(seed=7)
    earnings_syms = state.portfolio_symbols_with_earnings_within(7)
    if len(earnings_syms) < 2:
        # Try another seed that produces more earnings stocks
        sm, sid, targets, initial, state = _setup_session(seed=100)
        earnings_syms = state.portfolio_symbols_with_earnings_within(7)
    if len(earnings_syms) < 2:
        pytest.skip("no seed produced >=2 portfolio earnings stocks for this test")
    # Only create alert for first stock, skip the rest
    sym = earnings_syms[0]
    price = state.get_stock(sym).price
    state.create_price_alert(sym, "below", (price * Decimal("0.95")).quantize(Decimal("0.01")))

    task = get_task("rh_find_earnings_and_alert")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "missing alert should fail — bijection requires one alert per earnings stock"
    )


def test_wrong_price_fails():
    """Agent creates alerts at market price instead of 5% below."""
    sm, sid, targets, initial, state = _setup_session()
    earnings_syms = state.portfolio_symbols_with_earnings_within(7)
    assert len(earnings_syms) >= 1
    for sym in earnings_syms:
        price = state.get_stock(sym).price
        state.create_price_alert(sym, "below", price)  # at market, not 5% below

    task = get_task("rh_find_earnings_and_alert")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "alert at market price should fail — target_price predicate requires ~95% of price"
    )
