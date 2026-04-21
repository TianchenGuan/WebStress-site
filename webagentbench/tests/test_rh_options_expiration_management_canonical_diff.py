"""End-to-end tests for rh_options_expiration_management canonical_diff.

Task: For 8 expiring options positions, sell-to-close profitable longs,
buy-to-close short ITMs, and leave losing longs / short OTMs to expire.

Verifies:
  - Correct management (all required closings, no extras) passes.
  - Missing a sell-to-close fails.
  - Touching a no-action symbol fails.
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
        task_id="rh_options_expiration_management",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _sell_to_close(state, sym):
    pos = next(
        (p for p in state.options_positions if p.underlying_symbol == sym and p.position_side == "long"),
        None,
    )
    if pos:
        state.place_options_order(
            strategy="single",
            legs=[OptionsLeg(
                underlying_symbol=sym,
                option_type=pos.option_type,
                side="sell",
                strike=pos.strike_price,
                expiration=pos.expiration_date,
                quantity=1,
                premium=Decimal("1.00"),
            )],
        )


def _buy_to_close(state, sym):
    pos = next(
        (p for p in state.options_positions if p.underlying_symbol == sym and p.position_side == "short"),
        None,
    )
    if pos:
        state.place_options_order(
            strategy="single",
            legs=[OptionsLeg(
                underlying_symbol=sym,
                option_type=pos.option_type,
                side="buy",
                strike=pos.strike_price,
                expiration=pos.expiration_date,
                quantity=1,
                premium=Decimal("1.00"),
            )],
        )


def _do_full_management(state, targets):
    for sym in targets["profitable_long_symbols"]:
        _sell_to_close(state, sym)
    for sym in targets["short_itm_symbols"]:
        _buy_to_close(state, sym)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_full_management(state, targets)

    task = get_task("rh_options_expiration_management")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_sell_to_close_fails():
    """Agent skips closing one profitable long position."""
    sm, sid, targets, initial, state = _setup_session()
    prof_syms = targets["profitable_long_symbols"]

    # Close all but the first profitable long
    for sym in prof_syms[1:]:
        _sell_to_close(state, sym)
    for sym in targets["short_itm_symbols"]:
        _buy_to_close(state, sym)

    task = get_task("rh_options_expiration_management")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing sell-to-close should fail"


def test_touching_no_action_fails():
    """Agent unnecessarily closes a no-action position."""
    sm, sid, targets, initial, state = _setup_session()
    _do_full_management(state, targets)

    # Also touch a no-action symbol (losing long or short OTM)
    no_action = targets["no_action_symbols"]
    if no_action:
        sym = no_action[0]
        pos = next(
            (p for p in state.options_positions if p.underlying_symbol == sym),
            None,
        )
        if pos:
            side = "sell" if pos.position_side == "long" else "buy"
            state.place_options_order(
                strategy="single",
                legs=[OptionsLeg(
                    underlying_symbol=sym,
                    option_type=pos.option_type,
                    side=side,
                    strike=pos.strike_price,
                    expiration=pos.expiration_date,
                    quantity=1,
                    premium=Decimal("1.00"),
                )],
            )

    task = get_task("rh_options_expiration_management")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "touching no-action symbol should fail"
