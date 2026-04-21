"""End-to-end tests for rh_diagnose_portfolio_drop canonical_diff.

Task: Set price alerts at 5% below current price for each losing position.

Verifies:
  - Correct trajectory (alerts for all loss_symbols at ~95% price) passes.
  - Wrong price (not 5% below) fails.
  - Alert for non-loss symbol fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_diagnose_portfolio_drop",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    loss_syms = targets["loss_symbols"]
    assert len(loss_syms) >= 1

    for sym in loss_syms:
        price = state.get_stock(sym).price
        alert_price = (price * Decimal("0.95")).quantize(Decimal("0.01"))
        state.create_price_alert(sym, "below", alert_price)

    task = get_task("rh_diagnose_portfolio_drop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_alert_price_fails():
    """Agent sets alert at current price instead of 5% below."""
    sm, sid, targets, initial, state = _setup_session()
    loss_syms = targets["loss_symbols"]

    for sym in loss_syms:
        price = state.get_stock(sym).price
        state.create_price_alert(sym, "below", price)  # wrong: at market price

    task = get_task("rh_diagnose_portfolio_drop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "alert at market price should fail price predicate"


def test_extra_alert_fails():
    """Agent sets correct alerts plus an extra one for a non-loss symbol."""
    sm, sid, targets, initial, state = _setup_session()
    loss_syms = targets["loss_symbols"]

    for sym in loss_syms:
        price = state.get_stock(sym).price
        alert_price = (price * Decimal("0.95")).quantize(Decimal("0.01"))
        state.create_price_alert(sym, "below", alert_price)

    # Extra alert for non-loss symbol
    all_syms = [p.symbol for p in state.positions]
    non_loss = [s for s in all_syms if s not in loss_syms]
    if non_loss:
        price = state.get_stock(non_loss[0]).price
        state.create_price_alert(non_loss[0], "below", price * Decimal("0.95"))

    task = get_task("rh_diagnose_portfolio_drop")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "extra alert for non-loss symbol should fail"
