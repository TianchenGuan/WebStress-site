"""End-to-end tests for booking_notification_driven_action canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_notification_driven_action'


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
        # Mark notification as read
        notif = next(n for n in state.notifications if n.id == targets['notification_id'])
        notif.read = True
        # Add property to the saved list
        lst = next(l for l in state.saved_lists if l.id == targets['list_id'])
        if targets['property_id'] not in lst.property_ids:
            lst.property_ids.append(targets['property_id'])
        from datetime import datetime, timezone
        lst.updated_at = datetime.now(timezone.utc)
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_notification_not_read_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    # Only add property to list, don't mark notification as read
    lst = next(l for l in state.saved_lists if l.id == targets['list_id'])
    lst.property_ids.append(targets['property_id'])
    from datetime import datetime, timezone
    lst.updated_at = datetime.now(timezone.utc)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "not marking notification as read should fail"


def test_property_not_in_list_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    # Only mark notification as read, don't add property to list
    notif = next(n for n in state.notifications if n.id == targets['notification_id'])
    notif.read = True
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "not adding property to list should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
