"""End-to-end tests for rh_quarterly_performance_review canonical_diff.

Task: (1) Sell worst position via market order, (2) set 10%±alerts for best
position, (3) mark all notifications read, (4) create Corporate Actions Watch
watchlist with corporate action symbols.

Verifies:
  - Correct full trajectory passes.
  - Missing watchlist creation fails.
  - Missing notification marks fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_quarterly_performance_review",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_full_review(state, targets):
    worst = targets["worst_symbol"]
    best = targets["best_symbol"]

    # (1) Sell worst position via market order
    pos = state.get_position(worst)
    if pos:
        state.place_order(symbol=worst, side="sell", order_type="market", quantity=pos.quantity)

    # (2) Set price alerts for best position at +10% and -10%
    best_price = state.get_stock(best).price
    state.create_price_alert(symbol=best, condition="above", target_price=best_price * Decimal("1.10"))
    state.create_price_alert(symbol=best, condition="below", target_price=best_price * Decimal("0.90"))

    # (3) Mark all notifications as read
    for n in state.notifications:
        if not n.is_read:
            state.mark_notification_read(n.id)

    # (4) Create Corporate Actions Watch watchlist
    corp_syms = [sym for sym in state.corporate_action_symbols() if sym in state.owned_symbols()]
    state.create_watchlist(name="Corporate Actions Watch", symbols=corp_syms)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_full_review(state, targets)

    task = get_task("rh_quarterly_performance_review")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_watchlist_fails():
    """Agent skips creating the Corporate Actions Watch watchlist."""
    sm, sid, targets, initial, state = _setup_session()
    worst = targets["worst_symbol"]
    best = targets["best_symbol"]

    pos = state.get_position(worst)
    if pos:
        state.place_order(symbol=worst, side="sell", order_type="market", quantity=pos.quantity)
    best_price = state.get_stock(best).price
    state.create_price_alert(symbol=best, condition="above", target_price=best_price * Decimal("1.10"))
    state.create_price_alert(symbol=best, condition="below", target_price=best_price * Decimal("0.90"))
    for n in state.notifications:
        if not n.is_read:
            state.mark_notification_read(n.id)
    # No watchlist creation

    task = get_task("rh_quarterly_performance_review")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing watchlist should fail"


def test_missing_notification_marks_fails():
    """Agent skips marking all notifications as read."""
    sm, sid, targets, initial, state = _setup_session()
    worst = targets["worst_symbol"]
    best = targets["best_symbol"]

    pos = state.get_position(worst)
    if pos:
        state.place_order(symbol=worst, side="sell", order_type="market", quantity=pos.quantity)
    best_price = state.get_stock(best).price
    state.create_price_alert(symbol=best, condition="above", target_price=best_price * Decimal("1.10"))
    state.create_price_alert(symbol=best, condition="below", target_price=best_price * Decimal("0.90"))
    # No notification marks
    corp_syms = [sym for sym in state.corporate_action_symbols() if sym in state.owned_symbols()]
    state.create_watchlist(name="Corporate Actions Watch", symbols=corp_syms)

    task = get_task("rh_quarterly_performance_review")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "not marking notifications should fail"
