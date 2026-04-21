"""End-to-end tests for rh_tax_optimization canonical_diff.

Task: Sell enough losing positions (held 30+ days, not recent buys) to offset short-term gains.

Verifies:
  - Correct harvest (sell eligible losses to offset gains) passes.
  - Wash sale violation (selling a recent-buy loss) fails.
  - Insufficient harvest (not enough losses sold) fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_tax_optimization",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_harvest(state, targets):
    """Sell all eligible loss positions (excluding recent buys)."""
    eligible = [s for s in targets["loss_symbols"] if s not in targets["recent_buy_symbols"]]
    for sym in eligible:
        pos = state.get_position(sym)
        if pos and pos.quantity > 0:
            state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_harvest(state, targets)

    task = get_task("rh_tax_optimization")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wash_sale_violation_fails():
    """Agent sells a recent-buy loss position, triggering a wash sale."""
    sm, sid, targets, initial, state = _setup_session()
    recent = targets["recent_buy_symbols"]
    if recent:
        pos = state.get_position(recent[0])
        if pos and pos.quantity > 0:
            state.place_order(symbol=recent[0], side="sell", order_type="market", quantity=pos.quantity)

    task = get_task("rh_tax_optimization")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wash sale violation should fail"


def test_insufficient_harvest_fails():
    """Agent sells only a partial lot, not enough to offset all gains."""
    sm, sid, targets, initial, state = _setup_session()
    eligible = [s for s in targets["loss_symbols"] if s not in targets["recent_buy_symbols"]]
    if eligible:
        # Sell only 1 share to ensure insufficient harvest
        state.place_order(symbol=eligible[0], side="sell", order_type="market", quantity=1)

    task = get_task("rh_tax_optimization")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "insufficient harvest should fail"
