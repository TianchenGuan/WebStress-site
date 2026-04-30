"""End-to-end tests for booking_view_reservation canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.base import AuditEntry
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_view_reservation'


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
        state.audit_log.append(AuditEntry(
            action='reservation.view',
            payload={'reservation_id': targets['reservation_id']},
        ))
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_reservation_id_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    state.audit_log.append(AuditEntry(
        action='reservation.view',
        payload={'reservation_id': 'res_wrong_id'},
    ))
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong reservation_id in audit log should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no audit entry should fail"
    assert report.score < 1.0
