"""End-to-end tests for rh_earnings_play_setup canonical_diff.

Task: Place a stop-loss sell order at 8% below current price and set a price
alert at 5% above current price for the target symbol (AAPL).

Verifies:
  - Correct trajectory (stop-loss + alert at correct prices) passes.
  - Wrong stop price (5% below instead of 8%) fails.
  - Missing price alert fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_earnings_play_setup",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    price = state.get_stock(sym).price

    stop_price = (price * Decimal("0.92")).quantize(Decimal("0.01"))
    alert_price = (price * Decimal("1.05")).quantize(Decimal("0.01"))
    pos = state.get_position(sym)
    qty = pos.quantity if pos else Decimal("10")

    state.place_order(
        symbol=sym, side="sell", order_type="stop",
        quantity=qty, stop_price=stop_price,
    )
    state.create_price_alert(sym, "above", alert_price)

    task = get_task("rh_earnings_play_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_stop_price_fails():
    """Agent sets stop-loss at 5% below instead of 8% below."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    price = state.get_stock(sym).price

    stop_price = (price * Decimal("0.95")).quantize(Decimal("0.01"))  # wrong: 5% not 8%
    alert_price = (price * Decimal("1.05")).quantize(Decimal("0.01"))
    pos = state.get_position(sym)
    qty = pos.quantity if pos else Decimal("10")

    state.place_order(
        symbol=sym, side="sell", order_type="stop",
        quantity=qty, stop_price=stop_price,
    )
    state.create_price_alert(sym, "above", alert_price)

    task = get_task("rh_earnings_play_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "stop-loss at 5% below (not 8%) should fail price predicate"


def test_missing_alert_fails():
    """Agent places stop-loss but skips the price alert."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    price = state.get_stock(sym).price

    stop_price = (price * Decimal("0.92")).quantize(Decimal("0.01"))
    pos = state.get_position(sym)
    qty = pos.quantity if pos else Decimal("10")

    state.place_order(
        symbol=sym, side="sell", order_type="stop",
        quantity=qty, stop_price=stop_price,
    )
    # No price alert created

    task = get_task("rh_earnings_play_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing price alert should fail"


def test_missing_stop_order_fails():
    """Agent sets price alert but skips the stop-loss order."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["symbol"]
    price = state.get_stock(sym).price

    alert_price = (price * Decimal("1.05")).quantize(Decimal("0.01"))
    state.create_price_alert(sym, "above", alert_price)
    # No stop order placed

    task = get_task("rh_earnings_play_setup")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing stop-loss order should fail"
