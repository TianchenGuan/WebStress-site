"""End-to-end tests for rh_cost_basis_reconciliation canonical_diff.

Task: Sell half of AAPL (37 shares) via limit at ask price; set price alert 10% below.

Verifies:
  - Correct trajectory passes.
  - Wrong sell quantity fails.
  - Missing price alert fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_cost_basis_reconciliation",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    qty = targets["sell_quantity"]
    stock = state.get_stock(sym)
    alert_price = (stock.price * Decimal("0.90")).quantize(Decimal("0.01"))

    state.place_order(
        symbol=sym, side="sell", order_type="limit",
        quantity=Decimal(qty), limit_price=stock.ask,
    )
    state.create_price_alert(sym, "below", alert_price)

    task = get_task("rh_cost_basis_reconciliation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_quantity_fails():
    """Agent sells full position (75 shares) instead of half (37)."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    stock = state.get_stock(sym)
    alert_price = (stock.price * Decimal("0.90")).quantize(Decimal("0.01"))

    state.place_order(
        symbol=sym, side="sell", order_type="limit",
        quantity=Decimal("75"),  # wrong: full position instead of half
        limit_price=stock.ask,
    )
    state.create_price_alert(sym, "below", alert_price)

    task = get_task("rh_cost_basis_reconciliation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "selling full position instead of half should fail"


def test_missing_alert_fails():
    """Agent places the sell order but skips the price alert."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    qty = targets["sell_quantity"]
    stock = state.get_stock(sym)

    state.place_order(
        symbol=sym, side="sell", order_type="limit",
        quantity=Decimal(qty), limit_price=stock.ask,
    )
    # No price alert created

    task = get_task("rh_cost_basis_reconciliation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing price alert should fail"
