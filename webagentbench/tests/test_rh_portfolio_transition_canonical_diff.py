"""End-to-end tests for rh_portfolio_transition canonical_diff.

Task: Sell low-yield positions (limit orders at bid), then buy top-3 highest
yield watchlist stocks + BND + SCHD.

Verifies:
  - Correct transition (sell all low-yield + all required buys) passes.
  - Missing BND buy fails.
  - Selling wrong positions fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_portfolio_transition",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_full_transition(state, targets):
    watchlist_name = targets["watchlist_name"]

    # Sell all low-yield positions at limit (bid price)
    for sym in state.positions_below_dividend_yield(Decimal("1")):
        stock = state.get_stock(sym)
        pos = state.get_position(sym)
        if pos and stock:
            state.place_order(
                symbol=sym,
                side="sell",
                order_type="limit",
                quantity=pos.quantity,
                limit_price=stock.bid,
            )

    # Buy top 3 highest-yield watchlist stocks
    for sym in state.top_yield_symbols_from_watchlist(watchlist_name, 3):
        state.place_order(symbol=sym, side="buy", order_type="market", quantity=Decimal("10"))

    # Buy BND and SCHD
    state.place_order(symbol="BND", side="buy", order_type="market", quantity=Decimal("10"))
    state.place_order(symbol="SCHD", side="buy", order_type="market", quantity=Decimal("10"))


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_full_transition(state, targets)

    task = get_task("rh_portfolio_transition")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_bnd_buy_fails():
    """Agent completes transition but forgets to buy BND."""
    sm, sid, targets, initial, state = _setup_session()
    watchlist_name = targets["watchlist_name"]

    for sym in state.positions_below_dividend_yield(Decimal("1")):
        stock = state.get_stock(sym)
        pos = state.get_position(sym)
        if pos and stock:
            state.place_order(
                symbol=sym,
                side="sell",
                order_type="limit",
                quantity=pos.quantity,
                limit_price=stock.bid,
            )
    for sym in state.top_yield_symbols_from_watchlist(watchlist_name, 3):
        state.place_order(symbol=sym, side="buy", order_type="market", quantity=Decimal("10"))
    # No BND buy
    state.place_order(symbol="SCHD", side="buy", order_type="market", quantity=Decimal("10"))

    task = get_task("rh_portfolio_transition")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing BND buy should fail"


def test_selling_non_low_yield_fails():
    """Agent sells a position that does not have low dividend yield."""
    sm, sid, targets, initial, state = _setup_session()
    watchlist_name = targets["watchlist_name"]

    low_yield_syms = set(state.positions_below_dividend_yield(Decimal("1")))
    # Sell a position that is NOT in the low-yield list
    wrong_pos = next((p for p in state.positions if p.symbol not in low_yield_syms), None)
    if wrong_pos is None:
        return  # All positions are low-yield; skip test
    stock = state.get_stock(wrong_pos.symbol)
    state.place_order(
        symbol=wrong_pos.symbol,
        side="sell",
        order_type="limit",
        quantity=wrong_pos.quantity,
        limit_price=stock.bid,
    )

    for sym in state.top_yield_symbols_from_watchlist(watchlist_name, 3):
        state.place_order(symbol=sym, side="buy", order_type="market", quantity=Decimal("10"))
    state.place_order(symbol="BND", side="buy", order_type="market", quantity=Decimal("10"))
    state.place_order(symbol="SCHD", side="buy", order_type="market", quantity=Decimal("10"))

    task = get_task("rh_portfolio_transition")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "selling non-low-yield position should fail"
