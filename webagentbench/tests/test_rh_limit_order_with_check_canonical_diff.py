"""End-to-end tests for rh_limit_order_with_check canonical_diff.

Task: "Check AMZN's current price, then place a limit buy order for 10 shares
at 5% below current price, good-till-cancelled."

Verifies:
  - Correct trajectory (10 AMZN limit buy at 95% of price, GTC) passes.
  - Wrong limit price (not ~5% below) fails.
  - Wrong quantity fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_limit_order_with_check",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    amzn_price = state.get_stock("AMZN").price
    limit_price = (amzn_price * Decimal("0.95")).quantize(Decimal("0.01"))
    state.place_order(
        symbol="AMZN",
        side="buy",
        order_type="limit",
        quantity=Decimal("10"),
        limit_price=limit_price,
        time_in_force="gtc",
    )

    task = get_task("rh_limit_order_with_check")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_limit_price_fails():
    """Agent uses 20% below market instead of 5%."""
    sm, sid, targets, initial, state = _setup_session()
    amzn_price = state.get_stock("AMZN").price
    limit_price = (amzn_price * Decimal("0.80")).quantize(Decimal("0.01"))
    state.place_order(
        symbol="AMZN",
        side="buy",
        order_type="limit",
        quantity=Decimal("10"),
        limit_price=limit_price,
        time_in_force="gtc",
    )

    task = get_task("rh_limit_order_with_check")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "limit price 20% below market should fail — limit_price predicate requires ~5% below"
    )


def test_wrong_quantity_fails():
    """Agent buys 5 shares instead of 10."""
    sm, sid, targets, initial, state = _setup_session()
    amzn_price = state.get_stock("AMZN").price
    limit_price = (amzn_price * Decimal("0.95")).quantize(Decimal("0.01"))
    state.place_order(
        symbol="AMZN",
        side="buy",
        order_type="limit",
        quantity=Decimal("5"),
        limit_price=limit_price,
        time_in_force="gtc",
    )

    task = get_task("rh_limit_order_with_check")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "5 shares instead of 10 should fail — quantity eq predicate requires 10"
    )
