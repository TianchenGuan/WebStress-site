"""End-to-end tests for rh_multi_leg_options canonical_diff.

Task: Execute iron condor on SPY (sell call + put at ~5% OTM, buy protective
wings 2% further out, all ~45-day expiry).

Verifies:
  - Correct iron condor (4-leg, correct strikes/expiry) passes.
  - Wrong structure (only 2 legs) fails.
  - Wrong expiry (outside 35-55 day window) fails.
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
        task_id="rh_multi_leg_options",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _make_iron_condor(state, sym, expiry):
    price = state.get_stock(sym).price
    # Short put (5% below), long put (7% below), short call (5% above), long call (7% above)
    short_put_strike = (price * Decimal("0.95")).quantize(Decimal("0.01"))
    long_put_strike = (price * Decimal("0.93")).quantize(Decimal("0.01"))
    short_call_strike = (price * Decimal("1.05")).quantize(Decimal("0.01"))
    long_call_strike = (price * Decimal("1.07")).quantize(Decimal("0.01"))

    legs = [
        OptionsLeg(underlying_symbol=sym, option_type="put", side="sell", strike=short_put_strike, expiration=expiry, quantity=1, premium=Decimal("2.00")),
        OptionsLeg(underlying_symbol=sym, option_type="put", side="buy", strike=long_put_strike, expiration=expiry, quantity=1, premium=Decimal("1.00")),
        OptionsLeg(underlying_symbol=sym, option_type="call", side="sell", strike=short_call_strike, expiration=expiry, quantity=1, premium=Decimal("2.00")),
        OptionsLeg(underlying_symbol=sym, option_type="call", side="buy", strike=long_call_strike, expiration=expiry, quantity=1, premium=Decimal("1.00")),
    ]
    return state.place_options_order(strategy="iron_condor", legs=legs)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    expiry = state.anchor_date() + datetime.timedelta(days=45)
    _make_iron_condor(state, sym, expiry)

    task = get_task("rh_multi_leg_options")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_leg_count_fails():
    """Agent only sells 2 legs (naked strangle) instead of 4-leg iron condor."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    price = state.get_stock(sym).price
    expiry = state.anchor_date() + datetime.timedelta(days=45)

    legs = [
        OptionsLeg(underlying_symbol=sym, option_type="put", side="sell", strike=(price * Decimal("0.95")).quantize(Decimal("0.01")), expiration=expiry, quantity=1, premium=Decimal("2.00")),
        OptionsLeg(underlying_symbol=sym, option_type="call", side="sell", strike=(price * Decimal("1.05")).quantize(Decimal("0.01")), expiration=expiry, quantity=1, premium=Decimal("2.00")),
    ]
    state.place_options_order(strategy="iron_condor", legs=legs)

    task = get_task("rh_multi_leg_options")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "2-leg strangle instead of 4-leg iron condor should fail"


def test_wrong_expiry_fails():
    """Agent uses 90-day expiry instead of 45-day."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    expiry = state.anchor_date() + datetime.timedelta(days=90)  # outside 35-55 window
    _make_iron_condor(state, sym, expiry)

    task = get_task("rh_multi_leg_options")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "90-day expiry (outside 35-55 window) should fail"
