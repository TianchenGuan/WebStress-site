"""End-to-end tests for booking_verify_no_overlap canonical_diff.

Task now seeds res_1 (Jun 10-15, booked 20 days ago) overlapping res_2
(Jun 12-17, booked 5 days ago). Agent must cancel the more recently booked
res_2 while leaving res_1 and res_3 untouched.
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
    """Cancel the more recently booked overlapping reservation (res_2)."""
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        # res_1 (Jun 10-15, booked 20 days ago) overlaps res_2 (Jun 12-17, booked 5 days ago).
        # The more recently booked is res_2 — cancel it by directly setting status
        # (bypasses the fee-check API and its room-availability side effects).
        res2 = next(r for r in state.reservations if r.id == targets['res_id_2'])
        res2.status = 'cancelled'
        state.touch()
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
