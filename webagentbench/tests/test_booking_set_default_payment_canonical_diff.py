"""End-to-end tests for booking_set_default_payment canonical_diff.

Constraints-only task (settings.default_payment_id + PaymentMethod.is_default).
The correct card is Amex ending in 1234.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_set_default_payment'


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


def _set_default_to_amex(state):
    """Set the Amex card ending in 1234 as the default payment."""
    amex = next(pm for pm in state.payment_methods if pm.card_type == 'Amex' and pm.last_four == '1234')
    for pm in state.payment_methods:
        pm.is_default = pm.id == amex.id
    state.settings.default_payment_id = amex.id


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        _set_default_to_amex(state)
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_card_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    visa = next(pm for pm in state.payment_methods if pm.card_type == 'Visa')
    for pm in state.payment_methods:
        pm.is_default = pm.id == visa.id
    state.settings.default_payment_id = visa.id
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong card type as default should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
    assert report.score < 1.0


def test_missing_payment_method_flag_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    amex = next(pm for pm in state.payment_methods if pm.card_type == 'Amex' and pm.last_four == '1234')
    state.settings.default_payment_id = amex.id
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "settings pointer alone should not satisfy the backend side effect"
