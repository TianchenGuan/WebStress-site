"""End-to-end tests for rh_set_price_alert canonical_diff.

Task: "Set a price alert for GOOGL when it goes above $180.00."

Verifies:
  - Correct trajectory (GOOGL above $180 alert created) passes with score 1.0.
  - Wrong symbol fails.
  - Wrong direction (below instead of above) fails.
  - Wrong price fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_set_price_alert",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.create_price_alert("GOOGL", "above", Decimal("180.00"))

    task = get_task("rh_set_price_alert")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_symbol_fails():
    """Agent creates alert for AAPL instead of GOOGL."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_price_alert("AAPL", "above", Decimal("180.00"))

    task = get_task("rh_set_price_alert")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "wrong symbol should fail — symbol eq predicate must reject AAPL"
    )


def test_wrong_direction_fails():
    """Agent sets alert for GOOGL below $180 instead of above."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_price_alert("GOOGL", "below", Decimal("180.00"))

    task = get_task("rh_set_price_alert")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "wrong direction (below) should fail — condition eq predicate must reject it"
    )


def test_wrong_price_fails():
    """Agent sets alert for GOOGL above $200 instead of $180."""
    sm, sid, targets, initial, state = _setup_session()
    state.create_price_alert("GOOGL", "above", Decimal("200.00"))

    task = get_task("rh_set_price_alert")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "wrong target price should fail — target_price eq predicate must reject $200"
    )
