"""End-to-end tests for rh_full_portfolio_rebalance_with_tax canonical_diff.

Task: Tax-aware rebalance to VTI 40%, VXUS 20%, BND 25%, GLD 15%.
Sell losers first, avoid wash sales, prefer long-term lots.

Verifies:
  - Correct trajectory (sells + buys into target funds) passes.
  - Buying non-target symbols fails.
  - No sells (missing rebalancing) fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TARGET_SYMBOLS = ["VTI", "VXUS", "BND", "GLD"]


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_full_portfolio_rebalance_with_tax",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    allocation = targets["target_allocation"]

    # Sell all non-target positions (avoiding wash sales)
    wash_risk = state.wash_sale_risk_symbols(30)
    for pos in [p for p in state.positions if not p.id.startswith("pos_decoy_")]:
        if pos.symbol not in TARGET_SYMBOLS and pos.symbol not in wash_risk:
            state.place_order(symbol=pos.symbol, side="sell", order_type="market", quantity=pos.quantity)

    # Buy into all 4 target funds
    total_value = sum(
        state.get_stock(s).price * Decimal("10")
        for s in TARGET_SYMBOLS
    )
    for sym in TARGET_SYMBOLS:
        state.place_order(symbol=sym, side="buy", order_type="market", quantity=Decimal("10"))

    task = get_task("rh_full_portfolio_rebalance_with_tax")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_buying_non_target_fails():
    """Agent buys into non-target symbols instead of VTI/VXUS/BND/GLD."""
    sm, sid, targets, initial, state = _setup_session()

    # Sell something
    for pos in [p for p in state.positions if not p.id.startswith("pos_decoy_")][:1]:
        state.place_order(symbol=pos.symbol, side="sell", order_type="market", quantity=pos.quantity)

    # Buy into wrong symbol (not in target allocation)
    state.place_order(symbol="AAPL", side="buy", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_full_portfolio_rebalance_with_tax")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "buying non-target symbols should fail"


def test_no_action_fails():
    """Agent makes no trades at all — no sells, no buys."""
    sm, sid, targets, initial, state = _setup_session()
    # No state mutations — just evaluate with empty diff

    task = get_task("rh_full_portfolio_rebalance_with_tax")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "no trades should fail the sell-orders-exist constraint"
