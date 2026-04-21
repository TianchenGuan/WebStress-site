"""End-to-end tests for rh_sector_concentration canonical_diff.

Task: Sell most overweight tech stock to bring Technology sector to ≤50%,
then buy SCHD with proceeds.

Verifies:
  - Correct rebalance (sell largest tech + buy SCHD) passes.
  - Missing SCHD buy fails.
  - Selling wrong stock fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_sector_concentration",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["largest_tech_symbol"]

    pos = state.get_position(sym)
    if pos and pos.quantity > 0:
        state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)
    state.place_order(symbol="SCHD", side="buy", order_type="market", quantity=Decimal("10"))

    task = get_task("rh_sector_concentration")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_schd_buy_fails():
    """Agent sells tech stock but skips buying SCHD."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["largest_tech_symbol"]

    pos = state.get_position(sym)
    if pos and pos.quantity > 0:
        state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)
    # No SCHD buy

    task = get_task("rh_sector_concentration")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing SCHD buy should fail"


def test_selling_wrong_stock_fails():
    """Agent sells a different stock instead of the most overweight tech."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["largest_tech_symbol"]

    # Sell a different (non-largest) stock
    wrong = next((p for p in state.positions if p.symbol != sym and not p.id.startswith("pos_decoy_")), None)
    if wrong:
        state.place_order(symbol=wrong.symbol, side="sell", order_type="market", quantity=wrong.quantity)
    state.place_order(symbol="SCHD", side="buy", order_type="market", quantity=Decimal("10"))

    task = get_task("rh_sector_concentration")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "selling wrong stock should fail"
