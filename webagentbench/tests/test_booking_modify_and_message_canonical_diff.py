"""End-to-end tests for booking_modify_and_message canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import Message
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_modify_and_message'


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


def _make_hotel_message(targets, suffix=""):
    return Message(
        id=f"msg_hotel{suffix}",
        property_id=targets['property_id'],
        property_name=targets['property_name'],
        reservation_id=targets['reservation_id'],
        subject="Modified reservation - late checkout request",
        body="Hi, I have updated my dates and would like to request late checkout at 2pm please.",
        sender="guest",
        read=False,
        created_at=datetime.now(timezone.utc),
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        # Modify reservation dates
        res = next(r for r in state.reservations if r.id == targets['reservation_id'])
        res.check_in = '2026-06-12'
        res.check_out = '2026-06-16'
        res.status = 'modified'
        # Send message to hotel
        state.messages.append(_make_hotel_message(targets, suffix=f"_{seed}"))
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_dates_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    res = next(r for r in state.reservations if r.id == targets['reservation_id'])
    res.check_in = '2026-06-15'  # wrong date
    res.check_out = '2026-06-19'
    res.status = 'modified'
    state.messages.append(_make_hotel_message(targets))
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong dates should fail"


def test_missing_late_checkout_in_body_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    res = next(r for r in state.reservations if r.id == targets['reservation_id'])
    res.check_in = '2026-06-12'
    res.check_out = '2026-06-16'
    res.status = 'modified'
    msg = _make_hotel_message(targets)
    msg.body = "I have updated my reservation dates."  # missing late checkout
    state.messages.append(msg)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "missing late checkout in body should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
