"""End-to-end tests for rh_options_buy_call canonical_diff.

Task: Buy 1 AAPL call at nearest expiration, strike closest to current price.

Verifies:
  - Correct call buy on AAPL passes.
  - Buying a put instead fails.
  - Buying on wrong underlying fails.
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
        task_id="rh_options_buy_call",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _buy_aapl_call(state):
    chain = state.options_chains.get("AAPL", [])
    calls = [c for c in chain if c.option_type == "call"]
    earliest = min(c.expiration for c in calls)
    nearest_calls = [c for c in calls if c.expiration == earliest]
    aapl_price = state.get_stock("AAPL").price
    best = min(nearest_calls, key=lambda c: abs(c.strike - aapl_price))
    return state.place_options_order(
        strategy="single",
        legs=[OptionsLeg(
            underlying_symbol="AAPL",
            option_type="call",
            side="buy",
            strike=best.strike,
            expiration=best.expiration,
            quantity=1,
            premium=best.ask or Decimal("1.00"),
        )],
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _buy_aapl_call(state)

    task = get_task("rh_options_buy_call")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_option_type_fails():
    """Agent buys a put instead of a call on AAPL."""
    sm, sid, targets, initial, state = _setup_session()
    chain = state.options_chains.get("AAPL", [])
    puts = [c for c in chain if c.option_type == "put"]
    earliest = min(c.expiration for c in puts)
    nearest_puts = [c for c in puts if c.expiration == earliest]
    aapl_price = state.get_stock("AAPL").price
    best = min(nearest_puts, key=lambda c: abs(c.strike - aapl_price))
    state.place_options_order(
        strategy="single",
        legs=[OptionsLeg(
            underlying_symbol="AAPL",
            option_type="put",
            side="buy",
            strike=best.strike,
            expiration=best.expiration,
            quantity=1,
            premium=Decimal("1.00"),
        )],
    )

    task = get_task("rh_options_buy_call")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "buying put instead of call should fail"


def test_wrong_underlying_fails():
    """Agent buys call on MSFT instead of AAPL."""
    sm, sid, targets, initial, state = _setup_session()
    chain = state.options_chains.get("AAPL", [])
    calls = [c for c in chain if c.option_type == "call"]
    earliest = min(c.expiration for c in calls)
    nearest = [c for c in calls if c.expiration == earliest]
    aapl_price = state.get_stock("AAPL").price
    best = min(nearest, key=lambda c: abs(c.strike - aapl_price))
    state.place_options_order(
        strategy="single",
        legs=[OptionsLeg(
            underlying_symbol="MSFT",
            option_type="call",
            side="buy",
            strike=best.strike,
            expiration=best.expiration,
            quantity=1,
            premium=Decimal("1.00"),
        )],
    )

    task = get_task("rh_options_buy_call")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "buying call on wrong underlying should fail"
