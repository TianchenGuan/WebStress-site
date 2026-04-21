"""Tests for rh_live_watch_portfolio canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed=42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_watch_portfolio", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    best = targets["best_symbol"]
    pos = state.get_position(best)
    if pos:
        state.place_order(symbol=best, side="sell", order_type="market", quantity=pos.quantity)

    task = get_task("rh_live_watch_portfolio")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"


def test_selling_wrong_symbol_fails():
    sm, sid, targets, initial, state = _setup()
    best = targets["best_symbol"]
    wrong = next((p for p in state.positions if p.symbol != best and not p.id.startswith("pos_decoy_")), None)
    if wrong:
        state.place_order(symbol=wrong.symbol, side="sell", order_type="market", quantity=wrong.quantity)

    task = get_task("rh_live_watch_portfolio")
    report = match_diff(compute_diff(initial, state), task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False, "selling wrong symbol should fail"
