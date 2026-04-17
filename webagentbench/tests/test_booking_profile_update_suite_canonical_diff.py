"""End-to-end tests for booking_profile_update_suite canonical_diff.

Constraints-only task (Class 14 owner fields: owner_name, owner_phone, owner_nationality).
No-mutation test: score < 1.0 (penalty-only), NOT 0.0.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_profile_update_suite'


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
        state.owner_name = 'Jordan A. Parker'
        state.owner_phone = '+1-312-555-0198'
        state.owner_nationality = 'GB'
        # leave owner_email unchanged
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_name_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    state.owner_name = 'Wrong Name'
    state.owner_phone = '+1-312-555-0198'
    state.owner_nationality = 'GB'
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong name should fail"


def test_wrong_nationality_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    state.owner_name = 'Jordan A. Parker'
    state.owner_phone = '+1-312-555-0198'
    state.owner_nationality = 'US'  # wrong
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong nationality should fail"


def test_no_mutation_fails():
    """Constraints-only — score < 1.0 (penalty), NOT 0.0."""
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
    assert report.score < 1.0
