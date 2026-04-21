"""End-to-end tests for rh_covered_call_strategy canonical_diff.

Task: Sell a covered call on AAPL with ~30-day expiry and strike ~10% above current price.

Verifies:
  - Correct trajectory (valid covered call) passes.
  - Wrong strike price (at-the-money) fails.
  - Wrong expiry (too far out) fails.
"""

import datetime
from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.robinhood import OptionsLeg
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_covered_call_strategy",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    aapl_price = state.get_stock("AAPL").price
    strike = (aapl_price * Decimal("1.10")).quantize(Decimal("0.01"))
    expiry = state.anchor_date() + datetime.timedelta(days=30)

    leg = OptionsLeg(
        underlying_symbol="AAPL",
        option_type="call",
        side="sell",
        strike=strike,
        expiration=expiry,
        quantity=1,
        premium=Decimal("2.50"),
    )
    state.place_options_order(strategy="covered_call", legs=[leg])

    task = get_task("rh_covered_call_strategy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_strike_fails():
    """Agent uses at-the-money strike instead of 10% OTM."""
    sm, sid, targets, initial, state = _setup_session()
    aapl_price = state.get_stock("AAPL").price
    strike = aapl_price  # wrong: at-the-money, not 10% OTM
    expiry = state.anchor_date() + datetime.timedelta(days=30)

    leg = OptionsLeg(
        underlying_symbol="AAPL",
        option_type="call",
        side="sell",
        strike=strike,
        expiration=expiry,
        quantity=1,
        premium=Decimal("5.00"),
    )
    state.place_options_order(strategy="covered_call", legs=[leg])

    task = get_task("rh_covered_call_strategy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "ATM strike instead of 10% OTM should fail"


def test_wrong_expiry_fails():
    """Agent uses 90-day expiry instead of ~30-day."""
    sm, sid, targets, initial, state = _setup_session()
    aapl_price = state.get_stock("AAPL").price
    strike = (aapl_price * Decimal("1.10")).quantize(Decimal("0.01"))
    expiry = state.anchor_date() + datetime.timedelta(days=90)  # wrong: too far out

    leg = OptionsLeg(
        underlying_symbol="AAPL",
        option_type="call",
        side="sell",
        strike=strike,
        expiration=expiry,
        quantity=1,
        premium=Decimal("3.00"),
    )
    state.place_options_order(strategy="covered_call", legs=[leg])

    task = get_task("rh_covered_call_strategy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "90-day expiry (outside 21-45 window) should fail"
