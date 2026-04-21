"""End-to-end tests for rh_options_income_portfolio canonical_diff.

Task: Sell covered calls for 100+ share positions; sell cash-secured puts
for sub-100-share positions. All at nearest monthly expiry with delta ~0.30.

Verifies:
  - Full income strategy (covered calls + CSPs for all positions) passes.
  - Missing a covered call fails.
  - Buying instead of selling fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.robinhood import OptionsLeg
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 11):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_options_income_portfolio",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _nearest_call_strike(state, sym):
    """Find the ATM call at the nearest expiry that has an options chain."""
    chain = state.options_chains.get(sym, [])
    calls = [c for c in chain if c.option_type == "call"]
    if not calls:
        return None
    earliest = min(c.expiration for c in calls)
    nearest = [c for c in calls if c.expiration == earliest]
    price = state.get_stock(sym).price
    return min(nearest, key=lambda c: abs(c.strike - price))


def _nearest_put_strike(state, sym):
    chain = state.options_chains.get(sym, [])
    puts = [c for c in chain if c.option_type == "put"]
    if not puts:
        return None
    earliest = min(c.expiration for c in puts)
    nearest = [c for c in puts if c.expiration == earliest]
    price = state.get_stock(sym).price
    return min(nearest, key=lambda c: abs(c.strike - price))


def _do_full_income_strategy(state):
    for sym in state.position_symbols_at_or_above_shares(Decimal("100")):
        contract = _nearest_call_strike(state, sym)
        if contract:
            state.place_options_order(
                strategy="covered_call",
                legs=[OptionsLeg(
                    underlying_symbol=sym,
                    option_type="call",
                    side="sell",
                    strike=contract.strike,
                    expiration=contract.expiration,
                    quantity=1,
                    premium=contract.bid or Decimal("2.00"),
                )],
            )
    for pos in state.positions:
        if pos.quantity < Decimal("100"):
            contract = _nearest_put_strike(state, pos.symbol)
            if contract:
                state.place_options_order(
                    strategy="single",
                    legs=[OptionsLeg(
                        underlying_symbol=pos.symbol,
                        option_type="put",
                        side="sell",
                        strike=contract.strike,
                        expiration=contract.expiration,
                        quantity=1,
                        premium=contract.bid or Decimal("2.00"),
                    )],
                )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_full_income_strategy(state)

    task = get_task("rh_options_income_portfolio")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_covered_call_fails():
    """Agent skips covered call for one 100+ share position that has an options chain."""
    sm, sid, targets, initial, state = _setup_session()
    # Only consider symbols that have chains (others can't have covered calls anyway)
    chain_syms = [s for s in state.position_symbols_at_or_above_shares(Decimal("100")) if s in state.options_chains]
    assert len(chain_syms) >= 2, f"Need at least 2 chain syms; got {chain_syms}"

    # Sell covered calls for all chain symbols except the last
    for sym in chain_syms[:-1]:
        contract = _nearest_call_strike(state, sym)
        if contract:
            state.place_options_order(
                strategy="covered_call",
                legs=[OptionsLeg(
                    underlying_symbol=sym,
                    option_type="call",
                    side="sell",
                    strike=contract.strike,
                    expiration=contract.expiration,
                    quantity=1,
                    premium=Decimal("2.00"),
                )],
            )
    for pos in state.positions:
        if pos.quantity < Decimal("100"):
            contract = _nearest_put_strike(state, pos.symbol)
            if contract:
                state.place_options_order(
                    strategy="single",
                    legs=[OptionsLeg(
                        underlying_symbol=pos.symbol,
                        option_type="put",
                        side="sell",
                        strike=contract.strike,
                        expiration=contract.expiration,
                        quantity=1,
                        premium=Decimal("2.00"),
                    )],
                )

    task = get_task("rh_options_income_portfolio")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing covered call should fail"


def test_buying_instead_of_selling_fails():
    """Agent buys options instead of selling (wrong direction)."""
    sm, sid, targets, initial, state = _setup_session()

    for sym in state.position_symbols_at_or_above_shares(Decimal("100")):
        contract = _nearest_call_strike(state, sym)
        if contract:
            state.place_options_order(
                strategy="single",
                legs=[OptionsLeg(
                    underlying_symbol=sym,
                    option_type="call",
                    side="buy",
                    strike=contract.strike,
                    expiration=contract.expiration,
                    quantity=1,
                    premium=Decimal("2.00"),
                )],
            )

    task = get_task("rh_options_income_portfolio")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "buying instead of selling should fail"
