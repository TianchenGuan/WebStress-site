"""End-to-end tests for rh_check_buying_power canonical_diff.

Task: "Check your current buying power. Invest approximately half of it in AAPL
shares using a market buy order."

Verifies:
  - Correct trajectory (~50% of buying power in AAPL) passes with score 1.0.
  - Too small an amount fails the ~half constraint.
  - Wrong symbol fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_check_buying_power",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    aapl_price = state.get_stock("AAPL").price
    quantity = int(initial.buying_power / 2 / aapl_price)
    assert quantity > 0, "buying power must be enough to buy at least 1 share"
    state.place_order(
        symbol="AAPL",
        side="buy",
        order_type="market",
        quantity=Decimal(quantity),
    )

    task = get_task("rh_check_buying_power")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_too_small_amount_fails():
    """Agent buys only 1 share of AAPL — much less than half buying power."""
    sm, sid, targets, initial, state = _setup_session()
    state.place_order(
        symbol="AAPL",
        side="buy",
        order_type="market",
        quantity=Decimal("1"),
    )

    task = get_task("rh_check_buying_power")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "buying only 1 share should fail — order amount constraint requires ~50% of buying power"
    )


def test_wrong_symbol_fails():
    """Agent buys MSFT instead of AAPL."""
    sm, sid, targets, initial, state = _setup_session()
    msft_price = state.get_stock("MSFT").price
    quantity = int(initial.buying_power / 2 / msft_price)
    state.place_order(
        symbol="MSFT",
        side="buy",
        order_type="market",
        quantity=Decimal(max(quantity, 1)),
    )

    task = get_task("rh_check_buying_power")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "buying MSFT instead of AAPL should fail — symbol eq predicate requires AAPL"
    )
