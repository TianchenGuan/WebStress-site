"""End-to-end tests for rh_sell_loser_buy_winner canonical_diff.

Task: "Find the worst-performing stock in your portfolio by total return %.
Sell all of it, then buy more of your best-performing stock with the proceeds."

Verifies:
  - Correct trajectory (sell worst, buy best) passes with score 1.0.
  - Selling wrong symbol fails.
  - Selling worst but buying wrong symbol fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_sell_loser_buy_winner",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    worst = targets["worst_symbol"]
    best = targets["best_symbol"]
    worst_pos = state.get_position(worst)
    assert worst_pos is not None, "seed must have a worst-symbol position"
    # Sell all of worst
    state.place_order(symbol=worst, side="sell", order_type="market", quantity=worst_pos.quantity)
    # Buy some of best — use buying power (which now includes sell proceeds)
    best_price = state.get_stock(best).price
    buy_qty = int(state.buying_power / best_price)
    assert buy_qty >= 1, "buying power after sell must cover at least 1 share of best"
    state.place_order(symbol=best, side="buy", order_type="market", quantity=Decimal(buy_qty))

    task = get_task("rh_sell_loser_buy_winner")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_symbol_sold_fails():
    """Agent sells best performer instead of worst."""
    sm, sid, targets, initial, state = _setup_session()
    worst = targets["worst_symbol"]
    best = targets["best_symbol"]
    best_pos = state.get_position(best)
    assert best_pos is not None
    state.place_order(symbol=best, side="sell", order_type="market", quantity=best_pos.quantity)
    # Buy worst (wrong)
    worst_price = state.get_stock(worst).price
    worst_pos = state.get_position(worst)
    buy_qty = int(best_pos.quantity * state.get_stock(best).price / worst_price)
    if buy_qty >= 1:
        state.place_order(symbol=worst, side="buy", order_type="market", quantity=Decimal(buy_qty))

    task = get_task("rh_sell_loser_buy_winner")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "selling best/buying worst should fail — sell order predicate requires worst_symbol"
    )
