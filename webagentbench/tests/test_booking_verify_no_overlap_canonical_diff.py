"""End-to-end tests for booking_verify_no_overlap canonical_diff.

Constraints-only no-op task. All 3 reservations must remain confirmed.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_verify_no_overlap'


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
    """No-op: all reservations remain confirmed, no mutations needed."""
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_cancelling_a_reservation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    res = next(r for r in state.reservations if r.id == targets['res_id_1'])
    res.status = 'cancelled'
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "cancelling a reservation should fail"


def test_constraint_fails_when_reservation_not_confirmed():
    targets, initial_snap, initial_dict, state = _setup_session()
    res = next(r for r in state.reservations if r.id == targets['res_id_2'])
    res.status = 'modified'
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "non-confirmed target reservation should fail constraint"
