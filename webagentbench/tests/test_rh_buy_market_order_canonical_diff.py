"""End-to-end tests for rh_buy_market_order canonical_diff.

Task: "Buy 3 shares of {target.symbol} at market price."

Verifies:
  - Correct trajectory (market buy 3 shares of AAPL) passes with score 1.0.
  - Wrong-field trajectory (wrong symbol) fails.
  - Excess trajectory (buys target correctly AND one extra buy) fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_buy_market_order",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.place_order(
        symbol=targets["symbol"],
        side="buy",
        order_type="market",
        quantity=Decimal("3"),
    )

    task = get_task("rh_buy_market_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_symbol_fails():
    """Agent buys shares of the wrong symbol."""
    sm, sid, targets, initial, state = _setup_session()
    wrong = next(
        s.symbol for s in state.stocks
        if s.symbol != targets["symbol"]
    )
    state.place_order(
        symbol=wrong,
        side="buy",
        order_type="market",
        quantity=Decimal("3"),
    )

    task = get_task("rh_buy_market_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "buying the wrong symbol should fail — the symbol predicate must reject it"
    )


def test_wrong_quantity_fails():
    """Agent buys 1 share instead of 3."""
    sm, sid, targets, initial, state = _setup_session()
    state.place_order(
        symbol=targets["symbol"],
        side="buy",
        order_type="market",
        quantity=Decimal("1"),
    )

    task = get_task("rh_buy_market_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "buying 1 share instead of 3 should fail — quantity predicate must reject it"
    )


def test_excess_buy_fails():
    """Agent buys the correct 3 shares AND places an extra buy on another symbol."""
    sm, sid, targets, initial, state = _setup_session()
    state.place_order(
        symbol=targets["symbol"],
        side="buy",
        order_type="market",
        quantity=Decimal("3"),
    )
    extra = next(
        s.symbol for s in state.stocks
        if s.symbol != targets["symbol"]
    )
    state.place_order(
        symbol=extra,
        side="buy",
        order_type="market",
        quantity=Decimal("1"),
    )

    task = get_task("rh_buy_market_order")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "placing an extra buy order should trigger unaccounted-mutation failure"
    )
