"""End-to-end tests for rh_live_alert_and_buy canonical_diff.

Task: Set AAPL below-$182 alert; when it triggers, buy 5 shares at market.

Verifies:
  - Creating alert + placing buy passes.
  - Missing buy order fails.
  - Wrong symbol fails.
"""

from decimal import Decimal

from webagentbench.backend.price_engine import cascade_update
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="robinhood", task_id="rh_live_alert_and_buy", seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.create_price_alert(symbol="AAPL", condition="below", target_price=Decimal("182"))
    cascade_update(state, {"AAPL": Decimal("181.00")}, state._price_engine)
    state.place_order(symbol="AAPL", side="buy", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_live_alert_and_buy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=dict(targets), initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_missing_buy_fails():
    sm, sid, targets, initial, state = _setup_session()
    state.create_price_alert(symbol="AAPL", condition="below", target_price=Decimal("182"))
    cascade_update(state, {"AAPL": Decimal("181.00")}, state._price_engine)

    task = get_task("rh_live_alert_and_buy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=dict(targets), initial=initial, final=state)
    assert report.passed is False, "missing buy should fail"


def test_missing_alert_fails():
    sm, sid, targets, initial, state = _setup_session()
    state.place_order(symbol="AAPL", side="buy", order_type="market", quantity=Decimal("5"))

    task = get_task("rh_live_alert_and_buy")
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=dict(targets), initial=initial, final=state)
    assert report.passed is False, "missing alert should fail"
