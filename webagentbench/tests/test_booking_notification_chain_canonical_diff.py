"""End-to-end tests for booking_notification_chain canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import SavedList
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_notification_chain'


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
        # Cancel the target reservation
        res = next(r for r in state.reservations if r.id == targets['reservation_id'])
        res.status = 'cancelled'
        # Mark notification as read
        notif = next(n for n in state.notifications if n.id == targets['notification_id'])
        notif.read = True
        # Create "Revisit Later" saved list with target property
        state.saved_lists.append(SavedList(
            id=f"list_revisit_{seed}",
            name="Revisit Later",
            property_ids=[targets['property_id']],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_reservation_not_cancelled_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    notif = next(n for n in state.notifications if n.id == targets['notification_id'])
    notif.read = True
    state.saved_lists.append(SavedList(
        id="list_revisit",
        name="Revisit Later",
        property_ids=[targets['property_id']],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))
    # No cancellation
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "not cancelling reservation should fail"


def test_wrong_list_name_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    res = next(r for r in state.reservations if r.id == targets['reservation_id'])
    res.status = 'cancelled'
    notif = next(n for n in state.notifications if n.id == targets['notification_id'])
    notif.read = True
    state.saved_lists.append(SavedList(
        id="list_revisit",
        name="Later Visits",  # wrong name
        property_ids=[targets['property_id']],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong list name should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
