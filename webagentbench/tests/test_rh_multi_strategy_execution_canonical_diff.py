"""End-to-end tests for rh_multi_strategy_execution canonical_diff.

Task: (a) Tax-loss harvest positions with >$500 unrealized losses,
(b) protective collar on AAPL (buy put + sell call),
(c) weekly $100 recurring for SQ, PLTR, NVDA.

Verifies:
  - Correct multi-strategy trajectory passes.
  - Missing the collar fails.
  - Selling AAPL (protected stock) fails.
"""

import datetime
from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.robinhood import OptionsLeg
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

WATCHLIST_SYMS = ["SQ", "PLTR", "NVDA"]


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_multi_strategy_execution",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_full_strategy(state):
    anchor = state.anchor_date()
    aapl_price = state.get_stock("AAPL").price

    # (a) Tax-loss harvest: sell a non-AAPL losing position
    for pos in state.positions:
        if pos.symbol != "AAPL" and not pos.id.startswith("pos_decoy_"):
            state.place_order(symbol=pos.symbol, side="sell", order_type="market", quantity=pos.quantity)
            break  # sell just one for the test

    # (b) Protective collar on AAPL
    put_strike = (aapl_price * Decimal("0.95")).quantize(Decimal("0.01"))
    call_strike = (aapl_price * Decimal("1.05")).quantize(Decimal("0.01"))
    expiry = anchor + datetime.timedelta(days=45)
    state.place_options_order(strategy="protective_put", legs=[
        OptionsLeg(underlying_symbol="AAPL", option_type="put", side="buy", strike=put_strike, expiration=expiry, quantity=1, premium=Decimal("3.00")),
    ])
    state.place_options_order(strategy="covered_call", legs=[
        OptionsLeg(underlying_symbol="AAPL", option_type="call", side="sell", strike=call_strike, expiration=expiry, quantity=1, premium=Decimal("2.00")),
    ])

    # (c) Weekly $100 recurring for each watchlist symbol
    for sym in WATCHLIST_SYMS:
        state.create_recurring_investment(
            symbol=sym,
            amount=Decimal("100"),
            frequency="weekly",
            next_execution_date=anchor + datetime.timedelta(days=7),
        )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_full_strategy(state)

    task = get_task("rh_multi_strategy_execution")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_collar_fails():
    """Agent does tax-loss harvesting and recurring but skips the collar."""
    sm, sid, targets, initial, state = _setup_session()
    anchor = state.anchor_date()

    # Only do tax-loss + recurring, skip collar
    for pos in state.positions:
        if pos.symbol != "AAPL" and not pos.id.startswith("pos_decoy_"):
            state.place_order(symbol=pos.symbol, side="sell", order_type="market", quantity=pos.quantity)
            break

    for sym in WATCHLIST_SYMS:
        state.create_recurring_investment(
            symbol=sym,
            amount=Decimal("100"),
            frequency="weekly",
            next_execution_date=anchor + datetime.timedelta(days=7),
        )

    task = get_task("rh_multi_strategy_execution")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing collar should fail"


def test_selling_aapl_fails():
    """Agent sells AAPL (the protected stock) instead of another position."""
    sm, sid, targets, initial, state = _setup_session()
    anchor = state.anchor_date()
    aapl_price = state.get_stock("AAPL").price
    aapl_pos = state.get_position("AAPL")

    # Sell AAPL (wrong — cross-goal violation)
    state.place_order(symbol="AAPL", side="sell", order_type="market", quantity=aapl_pos.quantity)

    # Do collar + recurring anyway
    put_strike = (aapl_price * Decimal("0.95")).quantize(Decimal("0.01"))
    call_strike = (aapl_price * Decimal("1.05")).quantize(Decimal("0.01"))
    expiry = anchor + datetime.timedelta(days=45)
    state.place_options_order(strategy="protective_put", legs=[
        OptionsLeg(underlying_symbol="AAPL", option_type="put", side="buy", strike=put_strike, expiration=expiry, quantity=1, premium=Decimal("3.00")),
    ])
    state.place_options_order(strategy="covered_call", legs=[
        OptionsLeg(underlying_symbol="AAPL", option_type="call", side="sell", strike=call_strike, expiration=expiry, quantity=1, premium=Decimal("2.00")),
    ])
    for sym in WATCHLIST_SYMS:
        state.create_recurring_investment(
            symbol=sym,
            amount=Decimal("100"),
            frequency="weekly",
            next_execution_date=anchor + datetime.timedelta(days=7),
        )

    task = get_task("rh_multi_strategy_execution")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "selling protected AAPL should fail"
