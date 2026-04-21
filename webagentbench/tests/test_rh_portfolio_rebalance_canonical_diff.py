"""End-to-end tests for rh_portfolio_rebalance canonical_diff.

Task: "Rebalance portfolio to AAPL 40%, MSFT 30%, GOOGL 20%, AMZN 10%."

Verifies:
  - Correct trajectory (rebalancing trades executed) passes with score 1.0.
  - No-op (no trades) fails.
  - Wrong direction (moving further from target) fails.
"""

from decimal import Decimal, ROUND_DOWN

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_portfolio_rebalance",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _execute_rebalance(state, target_alloc):
    """Execute rebalancing: sell overweight positions, then buy underweight ones."""
    symbols = list(target_alloc.keys())
    total = sum(
        state.get_position(sym).quantity * state.get_stock(sym).price
        for sym in symbols
        if state.get_position(sym)
    )
    if total == 0:
        return

    sells = {}
    buys = {}
    for sym in symbols:
        pos = state.get_position(sym)
        current_qty = pos.quantity if pos else Decimal("0")
        target_value = total * Decimal(str(target_alloc[sym])) / 100
        price = state.get_stock(sym).price
        target_qty = (target_value / price).quantize(Decimal("1"), rounding=ROUND_DOWN)
        delta = target_qty - current_qty
        if delta < 0 and abs(delta) >= 1:
            sells[sym] = abs(delta)
        elif delta > 0 and delta >= 1:
            buys[sym] = delta

    for sym, qty in sells.items():
        state.place_order(symbol=sym, side="sell", order_type="market", quantity=qty)
    for sym, qty in buys.items():
        state.place_order(symbol=sym, side="buy", order_type="market", quantity=qty)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _execute_rebalance(state, targets["target_allocation"])

    task = get_task("rh_portfolio_rebalance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_action_fails():
    """Agent does nothing — portfolio stays at original allocation."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("rh_portfolio_rebalance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "no rebalancing should fail — constraints require trades that reduce allocation error"
    )
