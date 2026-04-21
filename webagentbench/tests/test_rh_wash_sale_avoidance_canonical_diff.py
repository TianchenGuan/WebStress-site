"""End-to-end tests for rh_wash_sale_avoidance canonical_diff.

Task: Sell all loss positions, skipping any purchased within the last 30 days.

Verifies:
  - Correct harvest (sell eligible losses only) passes.
  - Wash sale violation (selling a recent-buy position) fails.
  - Selling a gain position fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_wash_sale_avoidance",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_harvest(state, targets):
    eligible = [s for s in targets["loss_symbols"] if s not in targets["recent_buy_symbols"]]
    for sym in eligible:
        pos = state.get_position(sym)
        if pos and pos.quantity > 0:
            state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_harvest(state, targets)

    task = get_task("rh_wash_sale_avoidance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wash_sale_violation_fails():
    """Agent sells a position bought within the last 30 days."""
    sm, sid, targets, initial, state = _setup_session()
    recent = targets["recent_buy_symbols"]
    if recent:
        pos = state.get_position(recent[0])
        if pos and pos.quantity > 0:
            state.place_order(symbol=recent[0], side="sell", order_type="market", quantity=pos.quantity)

    task = get_task("rh_wash_sale_avoidance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wash sale violation should fail"


def test_selling_gain_position_fails():
    """Agent sells a gain position (not a loss position)."""
    sm, sid, targets, initial, state = _setup_session()
    gains = targets["gain_symbols"]
    eligible_gain = next((s for s in gains if s not in targets["recent_buy_symbols"]), None)
    if eligible_gain:
        pos = state.get_position(eligible_gain)
        if pos and pos.quantity > 0:
            state.place_order(symbol=eligible_gain, side="sell", order_type="market", quantity=pos.quantity)

    task = get_task("rh_wash_sale_avoidance")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "selling a gain position should fail"
