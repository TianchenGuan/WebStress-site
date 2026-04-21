"""End-to-end tests for rh_options_covered_call canonical_diff.

Task: Sell 1 AAPL covered call at >=10% OTM strike, nearest monthly expiry (14-60 days).

Verifies:
  - Correct covered call (10%+ OTM, 14-60 days) passes.
  - Strike below 10% OTM fails.
  - Wrong expiry (outside 14-60 day range) fails.
  - Buying a call instead of selling fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.robinhood import OptionsLeg
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_options_covered_call",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _find_valid_call(state, aapl_price, min_days=14, max_days=60, min_otm=Decimal("1.10")):
    """Find an AAPL call strike >= 10% OTM with expiry in 14-60 days."""
    chain = state.options_chains.get("AAPL", [])
    calls = [
        c for c in chain
        if c.option_type == "call"
        and c.strike >= aapl_price * min_otm
        and min_days <= state.days_until(c.expiration) <= max_days
    ]
    if not calls:
        return None
    return min(calls, key=lambda c: (state.days_until(c.expiration), c.strike))


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    aapl_price = state.get_stock("AAPL").price
    contract = _find_valid_call(state, aapl_price)
    assert contract is not None, "No valid AAPL call found"

    state.place_options_order(
        strategy="covered_call",
        legs=[OptionsLeg(
            underlying_symbol="AAPL",
            option_type="call",
            side="sell",
            strike=contract.strike,
            expiration=contract.expiration,
            quantity=1,
            premium=contract.bid or Decimal("2.00"),
        )],
    )

    task = get_task("rh_options_covered_call")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_strike_too_close_fails():
    """Agent sells call at strike less than 10% above current price."""
    sm, sid, targets, initial, state = _setup_session()
    aapl_price = state.get_stock("AAPL").price

    # Find a strike close to ATM (< 10% OTM)
    chain = state.options_chains.get("AAPL", [])
    close_calls = [
        c for c in chain
        if c.option_type == "call"
        and c.strike < aapl_price * Decimal("1.10")
        and 14 <= state.days_until(c.expiration) <= 60
    ]
    if not close_calls:
        return  # No valid close calls; skip test
    contract = close_calls[0]
    state.place_options_order(
        strategy="covered_call",
        legs=[OptionsLeg(
            underlying_symbol="AAPL",
            option_type="call",
            side="sell",
            strike=contract.strike,
            expiration=contract.expiration,
            quantity=1,
            premium=Decimal("2.00"),
        )],
    )

    task = get_task("rh_options_covered_call")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "strike < 10% OTM should fail"


def test_expiry_too_short_fails():
    """Agent sells call with expiry < 14 days."""
    sm, sid, targets, initial, state = _setup_session()
    aapl_price = state.get_stock("AAPL").price

    chain = state.options_chains.get("AAPL", [])
    short_calls = [
        c for c in chain
        if c.option_type == "call"
        and c.strike >= aapl_price * Decimal("1.10")
        and state.days_until(c.expiration) < 14
    ]
    if not short_calls:
        return  # No short-dated calls; skip
    contract = short_calls[0]
    state.place_options_order(
        strategy="covered_call",
        legs=[OptionsLeg(
            underlying_symbol="AAPL",
            option_type="call",
            side="sell",
            strike=contract.strike,
            expiration=contract.expiration,
            quantity=1,
            premium=Decimal("2.00"),
        )],
    )

    task = get_task("rh_options_covered_call")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "expiry < 14 days should fail"


def test_buying_call_fails():
    """Agent buys a call instead of selling (wrong direction)."""
    sm, sid, targets, initial, state = _setup_session()
    aapl_price = state.get_stock("AAPL").price
    contract = _find_valid_call(state, aapl_price)
    assert contract is not None

    state.place_options_order(
        strategy="single",
        legs=[OptionsLeg(
            underlying_symbol="AAPL",
            option_type="call",
            side="buy",
            strike=contract.strike,
            expiration=contract.expiration,
            quantity=1,
            premium=Decimal("2.00"),
        )],
    )

    task = get_task("rh_options_covered_call")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "buying call instead of selling should fail"
