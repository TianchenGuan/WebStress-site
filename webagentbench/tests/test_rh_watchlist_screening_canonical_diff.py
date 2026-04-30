"""End-to-end tests for rh_watchlist_screening canonical_diff.

Task: Screen "Potential Buys" watchlist. Remove stocks failing all three criteria
(P/E<25, div yield>2%, price within 10% of 52-wk high). Place limit buy at 3%
below current price for each passing stock.

Verifies:
  - Correct trajectory (limit buys for all passing symbols at ~97% price) passes.
  - Wrong order price (at market) fails.
  - Missing order for one passing symbol fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_watchlist_screening",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    passing = targets["passing_symbols"]
    failing = targets["failing_all_symbols"]
    assert len(passing) >= 1, "seed must have at least one passing symbol"

    # Remove failing symbols from watchlist
    wl = state.watchlist_named(targets["watchlist_name"])
    for sym in failing:
        state.remove_from_watchlist(wl.id, sym)

    # Place limit buy for each passing symbol at 3% below current price
    for sym in passing:
        price = state.get_stock(sym).price
        limit_price = (price * Decimal("0.97")).quantize(Decimal("0.01"))
        qty = max(1, int(Decimal("500") / price))
        state.place_order(
            symbol=sym, side="buy", order_type="limit",
            quantity=Decimal(qty), limit_price=limit_price,
        )

    task = get_task("rh_watchlist_screening")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_price_fails():
    """Agent places limit orders at market price instead of 3% below."""
    sm, sid, targets, initial, state = _setup_session()
    passing = targets["passing_symbols"]

    for sym in passing:
        price = state.get_stock(sym).price
        qty = max(1, int(Decimal("500") / price))
        state.place_order(
            symbol=sym, side="buy", order_type="limit",
            quantity=Decimal(qty), limit_price=price,  # market price, not 3% below
        )

    task = get_task("rh_watchlist_screening")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "limit orders at market price should fail price predicate"


def test_missing_order_fails():
    """Agent only places orders for some passing symbols, skips one."""
    sm, sid, targets, initial, state = _setup_session()
    passing = targets["passing_symbols"]
    if len(passing) < 2:
        import pytest
        pytest.skip("need at least 2 passing symbols for this test")

    # Only place order for first passing symbol, skip the rest
    sym = passing[0]
    price = state.get_stock(sym).price
    limit_price = (price * Decimal("0.97")).quantize(Decimal("0.01"))
    state.place_order(
        symbol=sym, side="buy", order_type="limit",
        quantity=Decimal(1), limit_price=limit_price,
    )

    task = get_task("rh_watchlist_screening")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing orders for passing symbols should fail bijection"


def test_wrong_quantity_fails():
    """Agent places correctly priced orders but not the requested ~$500 sizing."""
    sm, sid, targets, initial, state = _setup_session()
    passing = targets["passing_symbols"]
    assert passing, "seed must have at least one passing symbol"

    for sym in passing:
        price = state.get_stock(sym).price
        limit_price = (price * Decimal("0.97")).quantize(Decimal("0.01"))
        correct_qty = max(1, int(Decimal("500") / price))
        state.place_order(
            symbol=sym, side="buy", order_type="limit",
            quantity=Decimal(correct_qty + 1), limit_price=limit_price,
        )

    task = get_task("rh_watchlist_screening")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "incorrect $500 sizing should fail"
