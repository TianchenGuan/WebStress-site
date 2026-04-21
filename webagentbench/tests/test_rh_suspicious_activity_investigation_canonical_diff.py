"""End-to-end tests for rh_suspicious_activity_investigation canonical_diff.

Task: Cancel orders placed during suspicious session window, then enable authenticator 2FA.

Verifies:
  - Cancelling suspicious orders + enabling 2FA passes.
  - Missing 2FA fails.
  - Cancelling extra (non-suspicious) orders fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_suspicious_activity_investigation",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _do_investigation(state, targets):
    for oid in targets["suspicious_order_ids"]:
        state.cancel_order(oid)
    state.update_settings(two_factor_method="authenticator")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _do_investigation(state, targets)

    task = get_task("rh_suspicious_activity_investigation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_missing_2fa_fails():
    """Agent cancels orders but skips enabling 2FA."""
    sm, sid, targets, initial, state = _setup_session()
    for oid in targets["suspicious_order_ids"]:
        state.cancel_order(oid)
    # No 2FA setup

    task = get_task("rh_suspicious_activity_investigation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing 2FA should fail"


def test_cancelling_wrong_orders_fails():
    """Agent cancels a non-suspicious order in addition to suspicious ones."""
    sm, sid, targets, initial, state = _setup_session()
    _do_investigation(state, targets)

    # Also cancel a non-suspicious order
    wrong = next(
        (o for o in state.orders if o.id not in targets["suspicious_order_ids"] and not o.id.startswith("ord_decoy_")),
        None,
    )
    if wrong:
        state.cancel_order(wrong.id)

    task = get_task("rh_suspicious_activity_investigation")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "cancelling extra orders should fail"
