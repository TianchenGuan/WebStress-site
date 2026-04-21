"""End-to-end tests for rh_cross_reference_1099 canonical_diff.

Task: For each 1099 discrepancy symbol still held, set a price alert at the
reported cost basis. Use 'above' if current price is below cost basis, 'below'
if current price is above.

Verifies:
  - Correct trajectory passes.
  - Wrong condition (always 'below' regardless of direction) fails.
  - Alert for non-discrepancy symbol fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_cross_reference_1099",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    disc_syms = targets["discrepancy_symbols"]
    bases = targets["reported_cost_bases"]

    for sym in disc_syms:
        cost_basis = Decimal(bases[sym])
        price = state.get_stock(sym).price
        condition = "above" if price < cost_basis else "below"
        state.create_price_alert(sym, condition, cost_basis)

    task = get_task("rh_cross_reference_1099")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_condition_fails():
    """Agent always uses 'below' regardless of price direction."""
    sm, sid, targets, initial, state = _setup_session()
    disc_syms = targets["discrepancy_symbols"]
    bases = targets["reported_cost_bases"]

    for sym in disc_syms:
        cost_basis = Decimal(bases[sym])
        state.create_price_alert(sym, "below", cost_basis)  # always below, wrong

    task = get_task("rh_cross_reference_1099")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    # For seed=42, both AAPL and TSLA have price < basis, so 'above' is correct
    # Using 'below' should fail the condition constraint
    all_wrong = all(
        state.get_stock(sym).price < Decimal(bases[sym])
        for sym in disc_syms
    )
    if all_wrong:
        assert report.passed is False, "wrong condition should fail"


def test_extra_alert_fails():
    """Agent sets alert for a non-discrepancy symbol too."""
    sm, sid, targets, initial, state = _setup_session()
    disc_syms = targets["discrepancy_symbols"]
    bases = targets["reported_cost_bases"]

    for sym in disc_syms:
        cost_basis = Decimal(bases[sym])
        price = state.get_stock(sym).price
        condition = "above" if price < cost_basis else "below"
        state.create_price_alert(sym, condition, cost_basis)

    # Extra alert for non-discrepancy symbol
    state.create_price_alert("MSFT", "below", Decimal("400"))

    task = get_task("rh_cross_reference_1099")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "alert for non-discrepancy symbol should fail"
