"""End-to-end tests for rh_tax_loss_harvest canonical_diff.

Task: Sell loss positions (avoiding recent-buy wash sales), then buy VOO with proceeds.

Verifies:
  - Correct harvest (sell losses + buy VOO) passes.
  - Missing VOO buy fails.
  - Wash sale violation (selling recent-buy position) fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_tax_loss_harvest",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_harvest(state, targets):
    """Sell all eligible loss positions (excluding recent buys), then buy VOO."""
    eligible = [s for s in targets["loss_symbols"] if s not in targets["recent_buy_symbols"] and s != "VOO"]
    for sym in eligible:
        pos = state.get_position(sym)
        if pos and pos.quantity > 0:
            state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)
    state.place_order(symbol="VOO", side="buy", order_type="market", quantity=Decimal("5"))


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_harvest(state, targets)

    task = get_task("rh_tax_loss_harvest")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_voo_buy_fails():
    """Agent harvests losses but skips buying VOO."""
    sm, sid, targets, initial, state = _setup_session()
    eligible = [s for s in targets["loss_symbols"] if s not in targets["recent_buy_symbols"] and s != "VOO"]
    for sym in eligible:
        pos = state.get_position(sym)
        if pos and pos.quantity > 0:
            state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)
    # No VOO buy

    task = get_task("rh_tax_loss_harvest")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing VOO buy should fail"


def test_wash_sale_violation_fails():
    """Agent sells a position purchased within the last 30 days."""
    sm, sid, targets, initial, state = _setup_session()
    recent = targets["recent_buy_symbols"]
    if recent:
        pos = state.get_position(recent[0])
        if pos and pos.quantity > 0:
            state.place_order(symbol=recent[0], side="sell", order_type="market", quantity=pos.quantity)
    state.place_order(symbol="VOO", side="buy", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_tax_loss_harvest")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wash sale violation should fail"
