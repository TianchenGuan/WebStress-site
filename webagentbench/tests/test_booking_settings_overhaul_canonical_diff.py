"""End-to-end tests for booking_settings_overhaul canonical_diff.

Constraints-only task (Class 14 settings: currency, language, deal_alerts, newsletter).
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_settings_overhaul'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial_snap = sm.get_initial_snapshot(sid)
    initial_dict = initial_snap.model_dump()
    state = sm.get_state(sid)
    return dict(targets), initial_snap, initial_dict, state


def _run(targets, initial_snap, initial_dict, state):
    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial_dict, state.model_dump())
    return match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial_snap, final=state)


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        state.settings.currency = 'EUR'
        state.settings.language = 'French'
        state.settings.deal_alerts = False
        state.settings.newsletter = True
        # leave email_notifications and two_factor_enabled unchanged
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_currency_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    state.settings.currency = 'GBP'
    state.settings.language = 'French'
    state.settings.deal_alerts = False
    state.settings.newsletter = True
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong currency should fail"


def test_wrong_language_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    state.settings.currency = 'EUR'
    state.settings.language = 'Spanish'
    state.settings.deal_alerts = False
    state.settings.newsletter = True
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong language should fail"


def test_accidentally_toggling_2fa_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    state.settings.currency = 'EUR'
    state.settings.language = 'French'
    state.settings.deal_alerts = False
    state.settings.newsletter = True
    state.settings.two_factor_enabled = not state.settings.two_factor_enabled
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "accidentally toggling 2FA should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
    assert report.score < 1.0
