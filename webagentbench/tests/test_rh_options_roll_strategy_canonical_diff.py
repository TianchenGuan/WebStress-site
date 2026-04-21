"""End-to-end tests for rh_options_roll_strategy canonical_diff.

Task: Roll a covered call on MSFT — buy back expiring call, sell new call
at next monthly expiry ~5% OTM.

Verifies:
  - Correct roll (buy-to-close + sell-to-open) passes.
  - Missing buy-to-close fails.
  - Missing sell-to-open fails.
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
        task_id="rh_options_roll_strategy",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _get_expiring_position(state, sym):
    return next(
        (p for p in state.options_positions if p.underlying_symbol == sym and state.days_until(p.expiration_date) <= 7),
        None,
    )


def _get_new_call_contract(state, sym):
    """Find an MSFT call that is ~5% OTM and 14-45 days out."""
    chain = state.options_chains.get(sym, [])
    price = state.get_stock(sym).price
    target_strike = price * Decimal("1.05")
    candidates = [
        c for c in chain
        if c.option_type == "call"
        and 14 <= state.days_until(c.expiration) <= 45
        and c.strike >= price * Decimal("1.03")
        and c.strike <= price * Decimal("1.07")
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c.strike - target_strike))


def _do_roll(state, targets):
    sym = targets["symbol"]
    pos = _get_expiring_position(state, sym)
    assert pos is not None, "No expiring call position found"

    # Buy to close
    state.place_options_order(
        strategy="single",
        legs=[OptionsLeg(
            underlying_symbol=sym,
            option_type="call",
            side="buy",
            strike=pos.strike_price,
            expiration=pos.expiration_date,
            quantity=1,
            premium=Decimal("1.00"),
        )],
    )

    # Sell to open new call
    new_contract = _get_new_call_contract(state, sym)
    assert new_contract is not None, "No suitable new call contract found"
    state.place_options_order(
        strategy="covered_call",
        legs=[OptionsLeg(
            underlying_symbol=sym,
            option_type="call",
            side="sell",
            strike=new_contract.strike,
            expiration=new_contract.expiration,
            quantity=1,
            premium=new_contract.bid or Decimal("2.00"),
        )],
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_roll(state, targets)

    task = get_task("rh_options_roll_strategy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_buy_to_close_fails():
    """Agent sells new call but skips buying back the expiring call."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    new_contract = _get_new_call_contract(state, sym)
    assert new_contract is not None

    state.place_options_order(
        strategy="covered_call",
        legs=[OptionsLeg(
            underlying_symbol=sym,
            option_type="call",
            side="sell",
            strike=new_contract.strike,
            expiration=new_contract.expiration,
            quantity=1,
            premium=Decimal("2.00"),
        )],
    )

    task = get_task("rh_options_roll_strategy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing buy-to-close should fail"


def test_missing_sell_to_open_fails():
    """Agent buys back expiring call but doesn't sell new one."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    pos = _get_expiring_position(state, sym)
    assert pos is not None

    state.place_options_order(
        strategy="single",
        legs=[OptionsLeg(
            underlying_symbol=sym,
            option_type="call",
            side="buy",
            strike=pos.strike_price,
            expiration=pos.expiration_date,
            quantity=1,
            premium=Decimal("1.00"),
        )],
    )

    task = get_task("rh_options_roll_strategy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing sell-to-open should fail"
