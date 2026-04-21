"""End-to-end tests for rh_dividend_income_report canonical_diff.

Task: Sell lowest-dividend-income stock (worst_yield_symbol), buy highest-yield
from Income Ideas watchlist.

Verifies:
  - Correct trajectory (sell worst, buy from watchlist) passes.
  - Selling wrong symbol fails.
  - Buying symbol not in watchlist fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_dividend_income_report",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    worst = targets["worst_yield_symbol"]
    wl_syms = targets["watchlist_symbols"]
    best_buy = state.highest_yield_symbol_from_watchlist("Income Ideas")
    assert best_buy in wl_syms

    worst_pos = state.get_position(worst)
    assert worst_pos is not None
    state.place_order(symbol=worst, side="sell", order_type="market", quantity=worst_pos.quantity)

    best_price = state.get_stock(best_buy).price
    buy_qty = max(1, int(Decimal("500") / best_price))
    state.place_order(symbol=best_buy, side="buy", order_type="market", quantity=Decimal(buy_qty))

    task = get_task("rh_dividend_income_report")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_sell_symbol_fails():
    """Agent sells a non-worst-yield symbol."""
    sm, sid, targets, initial, state = _setup_session()
    worst = targets["worst_yield_symbol"]
    wl_syms = targets["watchlist_symbols"]

    # Sell a position that's NOT the worst yield symbol
    all_pos = [p for p in state.positions if p.symbol != worst and not p.id.startswith("pos_decoy_")]
    if not all_pos:
        return  # skip if only one position
    wrong_sym = all_pos[0].symbol
    state.place_order(symbol=wrong_sym, side="sell", order_type="market", quantity=all_pos[0].quantity)

    best_buy = state.highest_yield_symbol_from_watchlist("Income Ideas")
    state.place_order(symbol=best_buy, side="buy", order_type="market", quantity=Decimal("1"))

    task = get_task("rh_dividend_income_report")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "selling wrong symbol should fail"


def test_buy_not_in_watchlist_fails():
    """Agent buys a symbol not in Income Ideas watchlist."""
    sm, sid, targets, initial, state = _setup_session()
    worst = targets["worst_yield_symbol"]
    wl_syms = targets["watchlist_symbols"]

    worst_pos = state.get_position(worst)
    state.place_order(symbol=worst, side="sell", order_type="market", quantity=worst_pos.quantity)

    # Buy something NOT in the watchlist
    off_watchlist = "AAPL"
    state.place_order(symbol=off_watchlist, side="buy", order_type="market", quantity=Decimal("1"))

    task = get_task("rh_dividend_income_report")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "buying non-watchlist symbol should fail"
