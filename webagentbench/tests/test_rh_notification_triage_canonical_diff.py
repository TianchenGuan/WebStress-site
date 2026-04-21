"""End-to-end tests for rh_notification_triage canonical_diff.

Task: Mark all unread order-fill notifications as read; set a price alert
at the fill price for any stock with >2% slippage.

Verifies:
  - Correct triage (mark all read + alerts for high-slippage stocks) passes.
  - Missing notification marks fails.
  - Missing price alerts fails.
  - Alerts for wrong symbols fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_notification_triage",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _mark_all_read(state):
    for n in state.notifications:
        if n.type == "order_fill" and not n.is_read:
            state.mark_notification_read(n.id)


def _create_slippage_alerts(state, targets):
    for sym in targets["high_slippage_symbols"]:
        order = next(
            (o for o in state.orders if o.symbol == sym and o.status == "filled"),
            None,
        )
        price = (
            order.filled_price
            if (order and order.filled_price is not None)
            else state.get_stock(sym).price
        )
        state.create_price_alert(symbol=sym, condition="above", target_price=price)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _mark_all_read(state)
    _create_slippage_alerts(state, targets)

    task = get_task("rh_notification_triage")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_notification_marks_fails():
    """Agent creates alerts but does not mark notifications as read."""
    sm, sid, targets, initial, state = _setup_session()
    _create_slippage_alerts(state, targets)

    task = get_task("rh_notification_triage")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "not marking notifications should fail"


def test_missing_alerts_fails():
    """Agent marks notifications but skips creating price alerts."""
    sm, sid, targets, initial, state = _setup_session()
    _mark_all_read(state)

    task = get_task("rh_notification_triage")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing price alerts should fail"


def test_wrong_symbol_alerts_fails():
    """Agent marks notifications and creates alerts for wrong symbols."""
    sm, sid, targets, initial, state = _setup_session()
    _mark_all_read(state)

    high_slippage = set(targets["high_slippage_symbols"])
    wrong_syms = [
        o.symbol for o in state.orders
        if o.symbol not in high_slippage and o.status == "filled"
    ][:2]
    for sym in wrong_syms:
        state.create_price_alert(
            symbol=sym,
            condition="above",
            target_price=state.get_stock(sym).price,
        )

    task = get_task("rh_notification_triage")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "alerts for wrong symbols should fail"
