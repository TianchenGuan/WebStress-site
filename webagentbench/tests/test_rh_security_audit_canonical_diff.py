"""End-to-end tests for rh_security_audit canonical_diff.

Task: Check security log for logins outside the US; if found, enable 2FA via authenticator app.

Verifies:
  - Enabling authenticator 2FA passes.
  - Setting wrong 2FA method (sms) fails.
  - Not enabling 2FA at all fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_security_audit",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    state.update_settings(two_factor_method="authenticator")

    task = get_task("rh_security_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_2fa_method_fails():
    """Agent sets 2FA to SMS instead of authenticator."""
    sm, sid, targets, initial, state = _setup_session()
    state.update_settings(two_factor_method="sms")

    task = get_task("rh_security_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wrong 2FA method should fail"


def test_no_action_fails():
    """Agent takes no action (does not enable 2FA)."""
    sm, sid, targets, initial, state = _setup_session()
    # No state changes

    task = get_task("rh_security_audit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "no action should fail"
