"""End-to-end tests for rh_margin_call_resolution canonical_diff.

Task: Sell the smallest-impact position (INTC), deposit $500 as buffer.

Verifies:
  - Correct trajectory (sell INTC + $500 deposit) passes.
  - Selling wrong symbol fails.
  - Missing deposit fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_margin_call_resolution",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["smallest_impact_symbol"]
    pos = state.get_position(sym)
    assert pos is not None
    bank = state.linked_banks[0]

    state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)
    state.initiate_transfer("deposit", Decimal("500"), bank.id)

    task = get_task("rh_margin_call_resolution")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_symbol_fails():
    """Agent sells wrong symbol instead of smallest-impact position."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["smallest_impact_symbol"]
    bank = state.linked_banks[0]

    # Sell a different symbol
    other_positions = [p for p in state.positions if p.symbol != sym and not p.id.startswith("pos_decoy_")]
    assert other_positions
    wrong_pos = other_positions[0]
    state.place_order(symbol=wrong_pos.symbol, side="sell", order_type="market", quantity=wrong_pos.quantity)
    state.initiate_transfer("deposit", Decimal("500"), bank.id)

    task = get_task("rh_margin_call_resolution")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "selling wrong symbol should fail"


def test_missing_deposit_fails():
    """Agent sells smallest-impact position but skips the $500 deposit."""
    sm, sid, targets, initial, state = _setup_session()
    sym = targets["smallest_impact_symbol"]
    pos = state.get_position(sym)

    state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)
    # No deposit

    task = get_task("rh_margin_call_resolution")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing $500 deposit should fail"
