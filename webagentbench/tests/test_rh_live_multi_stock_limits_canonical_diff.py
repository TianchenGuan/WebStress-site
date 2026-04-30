"""Tests for rh_live_multi_stock_limits canonical_diff.

Task: Place 3 limit buys (AAPL ≤$180, AMZN ≤$175, GOOGL ≤$165), then monitor
which fill. Per the seeded price_trajectory, AAPL and AMZN both dip below
their limits and fill; GOOGL is held flat at $171 and stays pending.

The canonical_diff requires:
  - AAPL + AMZN orders filled (status=filled, with positions/transactions/
    notifications side-effects matched).
  - GOOGL order remains status=pending — verifies the agent observed it
    didn't fill rather than paper-completing the task.
"""

from decimal import Decimal

from webagentbench.backend.price_engine import cascade_update
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood", task_id="rh_live_multi_stock_limits", seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _drive_aapl_amzn_fills(state) -> None:
    """Drop AAPL and AMZN below their limits; leave GOOGL untouched (still $171)."""
    cascade_update(
        state,
        {"AAPL": Decimal("178.00"), "AMZN": Decimal("173.00")},
        state._price_engine,
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="AAPL", side="buy", order_type="limit",
                      quantity=Decimal("10"), limit_price=Decimal("180"))
    state.place_order(symbol="AMZN", side="buy", order_type="limit",
                      quantity=Decimal("10"), limit_price=Decimal("175"))
    state.place_order(symbol="GOOGL", side="buy", order_type="limit",
                      quantity=Decimal("10"), limit_price=Decimal("165"))
    _drive_aapl_amzn_fills(state)

    task = get_task("rh_live_multi_stock_limits")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_missing_one_order_fails():
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="AAPL", side="buy", order_type="limit",
                      quantity=Decimal("10"), limit_price=Decimal("180"))
    state.place_order(symbol="AMZN", side="buy", order_type="limit",
                      quantity=Decimal("10"), limit_price=Decimal("175"))
    _drive_aapl_amzn_fills(state)

    task = get_task("rh_live_multi_stock_limits")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False, "missing GOOGL order should fail"


def test_all_pending_fails():
    """Placed but never waited — AAPL/AMZN should reach filled, fails otherwise."""
    sm, sid, targets, initial, state = _setup()
    state.place_order(symbol="AAPL", side="buy", order_type="limit",
                      quantity=Decimal("10"), limit_price=Decimal("180"))
    state.place_order(symbol="AMZN", side="buy", order_type="limit",
                      quantity=Decimal("10"), limit_price=Decimal("175"))
    state.place_order(symbol="GOOGL", side="buy", order_type="limit",
                      quantity=Decimal("10"), limit_price=Decimal("165"))

    task = get_task("rh_live_multi_stock_limits")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False, "AAPL/AMZN must reach filled status"
