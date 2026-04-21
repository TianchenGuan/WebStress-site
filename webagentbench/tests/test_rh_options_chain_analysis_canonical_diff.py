"""End-to-end tests for rh_options_chain_analysis canonical_diff.

Task: Buy 1 TSLA put with highest open interest expiring within 2 weeks.

Verifies:
  - Correct highest-OI contract purchase passes.
  - Wrong contract (different strike/expiry) fails.
  - Contract expiring beyond 2 weeks fails.
"""

import datetime
from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.robinhood import OptionsLeg
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_options_chain_analysis",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    contract = state.highest_open_interest_contract("TSLA", option_type="put", max_days=14)
    assert contract is not None, "No TSLA put contracts within 2 weeks"

    state.place_options_order(
        strategy="single",
        legs=[OptionsLeg(
            underlying_symbol="TSLA",
            option_type="put",
            side="buy",
            strike=contract.strike,
            expiration=contract.expiration,
            quantity=1,
            premium=contract.ask or Decimal("1.00"),
        )],
    )

    task = get_task("rh_options_chain_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_contract_fails():
    """Agent buys a different TSLA put (not highest OI) within 2 weeks."""
    sm, sid, targets, initial, state = _setup_session()
    best = state.highest_open_interest_contract("TSLA", option_type="put", max_days=14)
    assert best is not None

    chain = state.options_chains.get("TSLA", [])
    anchor_exp = min(c.expiration for c in chain)
    within_2w = [
        c for c in chain
        if c.option_type == "put"
        and (c.expiration - anchor_exp).days <= 14
        and (c.strike != best.strike or c.expiration != best.expiration)
    ]
    if not within_2w:
        return  # Only one valid contract; skip

    wrong = within_2w[0]
    state.place_options_order(
        strategy="single",
        legs=[OptionsLeg(
            underlying_symbol="TSLA",
            option_type="put",
            side="buy",
            strike=wrong.strike,
            expiration=wrong.expiration,
            quantity=1,
            premium=Decimal("1.00"),
        )],
    )

    task = get_task("rh_options_chain_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wrong contract should fail"


def test_expiry_beyond_2w_fails():
    """Agent buys a TSLA put expiring beyond 2 weeks from earliest."""
    sm, sid, targets, initial, state = _setup_session()
    chain = state.options_chains.get("TSLA", [])
    anchor_exp = min(c.expiration for c in chain)
    beyond = [
        c for c in chain
        if c.option_type == "put" and (c.expiration - anchor_exp).days > 14
    ]
    if not beyond:
        return  # No contracts beyond 2 weeks; skip

    contract = beyond[0]
    state.place_options_order(
        strategy="single",
        legs=[OptionsLeg(
            underlying_symbol="TSLA",
            option_type="put",
            side="buy",
            strike=contract.strike,
            expiration=contract.expiration,
            quantity=1,
            premium=Decimal("1.00"),
        )],
    )

    task = get_task("rh_options_chain_analysis")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "contract beyond 2 weeks should fail"
