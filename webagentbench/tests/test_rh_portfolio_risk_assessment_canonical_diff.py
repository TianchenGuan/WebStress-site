"""End-to-end tests for rh_portfolio_risk_assessment canonical_diff.

Task: (1) Sell concentrated positions (>25%), (2) close expiring options,
(3) deposit $5,000 to reduce margin utilization.

Verifies:
  - Correct trajectory (all 3 sub-tasks) passes.
  - Missing deposit fails.
  - Skipping concentrated sell fails.
"""

from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.robinhood import OptionsLeg
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_portfolio_risk_assessment",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_full_assessment(state):
    # (1) Sell concentrated positions (loop until none remain)
    seen = set()
    while True:
        conc = [s for s in state.concentrated_symbols(25.0) if s not in seen]
        if not conc:
            break
        sym = conc[0]
        seen.add(sym)
        pos = state.get_position(sym)
        if pos:
            state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)

    # (2) Close expiring options positions (within 5 days)
    for pos in state.expiring_options_positions(5):
        side = "sell" if pos.position_side == "long" else "buy"
        state.place_options_order(
            strategy="single",
            legs=[OptionsLeg(
                underlying_symbol=pos.underlying_symbol,
                option_type=pos.option_type,
                side=side,
                strike=pos.strike_price,
                expiration=pos.expiration_date,
                quantity=pos.quantity,
                premium=Decimal("1.00"),
            )],
        )

    # (3) Deposit $5,000
    bank = state.linked_banks[0]
    state.initiate_transfer("deposit", Decimal("5000"), bank.id)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_full_assessment(state)

    task = get_task("rh_portfolio_risk_assessment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_deposit_fails():
    """Agent sells concentrated positions and closes options but skips deposit."""
    sm, sid, targets, initial, state = _setup_session()

    for sym in state.concentrated_symbols(25.0):
        pos = state.get_position(sym)
        if pos:
            state.place_order(symbol=sym, side="sell", order_type="market", quantity=pos.quantity)

    for pos in state.expiring_options_positions(5):
        side = "sell" if pos.position_side == "long" else "buy"
        state.place_options_order(
            strategy="single",
            legs=[OptionsLeg(
                underlying_symbol=pos.underlying_symbol,
                option_type=pos.option_type,
                side=side,
                strike=pos.strike_price,
                expiration=pos.expiration_date,
                quantity=pos.quantity,
                premium=Decimal("1.00"),
            )],
        )

    task = get_task("rh_portfolio_risk_assessment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing deposit should fail"


def test_skipping_concentrated_sell_fails():
    """Agent deposits and closes options but skips selling concentrated positions."""
    sm, sid, targets, initial, state = _setup_session()
    conc_syms = state.concentrated_symbols(25.0)
    assert conc_syms, "Need at least one concentrated symbol for this test"

    for pos in state.expiring_options_positions(5):
        side = "sell" if pos.position_side == "long" else "buy"
        state.place_options_order(
            strategy="single",
            legs=[OptionsLeg(
                underlying_symbol=pos.underlying_symbol,
                option_type=pos.option_type,
                side=side,
                strike=pos.strike_price,
                expiration=pos.expiration_date,
                quantity=pos.quantity,
                premium=Decimal("1.00"),
            )],
        )

    bank = state.linked_banks[0]
    state.initiate_transfer("deposit", Decimal("5000"), bank.id)

    task = get_task("rh_portfolio_risk_assessment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "skipping concentrated sell should fail"
